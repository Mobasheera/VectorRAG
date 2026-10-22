// =========================================================
// ADAPTIVE RAG CONTENT SCRIPT
// One detection engine + feature layers on top
// =========================================================

console.log("[RAG] content.js loaded!");

// =========================================================
// STATE
// =========================================================
let lastDetectedAnswer = "";   // prevents duplicate sends
let lastUserPrompt = "";       // for prompt-change detection
let lastUrl = location.href;   // for new-chat detection
let domHadMessages = false;    // for new-chat detection

let tickTimer = null;          // single 10-second timer
let streamEndTimer = null;     // debounce for streaming observer
let observer = null;           // DOM mutation observer

// =========================================================
// HELPERS
// =========================================================
function cleanText(t) {
    if (!t) return "";
    return String(t).replace(/\s+/g, " ").trim();
}

function getPlatform() {
    const h = location.hostname.toLowerCase();
    if (h.includes("chatgpt") || h.includes("openai")) return "ChatGPT";
    if (h.includes("gemini")) return "Gemini";
    if (h.includes("claude")) return "Claude";
    if (h.includes("copilot")) return "Copilot";
    if (h.includes("perplexity")) return "Perplexity";
    return "AI";
}

// =========================================================
// SELECTORS
// =========================================================
function getResponseSelectors() {
    const platform = getPlatform();

    if (platform === "ChatGPT") {
        return ['[data-message-author-role="assistant"]'];
    }
    if (platform === "Gemini") {
        return [
            'model-response',
            'message-content.model-response-text',
            '.model-response-text',
            '.markdown-main-panel',
            'response-container',
            '[data-response-index]',
            '.response-content',
            '[id*="model-response"]',
            '[class*="model-response"]',
            '[class*="response-content"]'
        ];
    }
    if (platform === "Claude") {
        return ['.font-claude-message', '[data-is-streaming]'];
    }
    if (platform === "Copilot") {
        return ['[data-content="ai-message"]', '[class*="ai-message"]'];
    }
    // Generic fallback
    return [
        '[data-message-author-role="assistant"]',
        '.markdown',
        '.prose',
        '[class*="assistant"]',
        '[class*="response"]'
    ];
}

function getUserPromptSelectors() {
    return [
        '[data-message-author-role="user"]',
        '[data-testid*="user"]',
        '[class*="user-message"]',
        '[class*="human-message"]'
    ];
}

// =========================================================
// DOM PROBES
// =========================================================
function getLatestResponse() {
    const selectors = getResponseSelectors();

    for (const sel of selectors) {
        const els = document.querySelectorAll(sel);
        if (!els.length) continue;

        const last = els[els.length - 1];
        const txt = cleanText(last.innerText || last.textContent || "");
        if (txt.length > 20) return txt;
    }
    return "";
}

function getLatestUserPrompt() {
    const selectors = getUserPromptSelectors();
    for (const sel of selectors) {
        const els = document.querySelectorAll(sel);
        if (els.length > 0) {
            const last = els[els.length - 1];
            const txt = cleanText(last.innerText || last.textContent || "");
            if (txt) return txt;
        }
    }
    return "";
}

function domHasAnyMessages() {
    const probes = [
        '[data-message-author-role="user"]',
        '[data-message-author-role="assistant"]',
        'model-response',
        'message-content'
    ];
    for (const sel of probes) {
        if (document.querySelector(sel)) return true;
    }
    return false;
}

// =========================================================
// SEND HELPERS
// =========================================================
async function storeResponse(answer) {
    try {
        await chrome.storage.local.set({
            latestAnswer: answer,
            platform: getPlatform(),
            sourceWebsite: location.hostname,
            sourceURL: location.href,
            detectedAt: new Date().toISOString()
        });
    } catch (_) {}
}

async function notifySidePanel(answer) {
    try {
        await chrome.runtime.sendMessage({
            type: "NEW_AI_RESPONSE",
            answer: answer,
            platform: getPlatform(),
            website: location.hostname,
            url: location.href
        });
    } catch (_) {}

    // Also send the "background" version so it can preserve/adjust results
    try {
        await chrome.runtime.sendMessage({
            type: "AI_RESPONSE_DETECTED",
            answer: answer,
            platform: getPlatform(),
            website: location.hostname,
            url: location.href
        });
    } catch (_) {}
}

async function notifyUIReset() {
    try {
        await chrome.storage.local.remove([
            "latestAnswer",
            "latestResult",
            "platform",
            "sourceWebsite",
            "sourceURL",
            "detectedAt"
        ]);
    } catch (_) {}

    try {
        await chrome.runtime.sendMessage({
            type: "UI_RESET",
            answer: "",
            platform: "Waiting...",
            website: "",
            url: ""
        });
    } catch (_) {}
}

// =========================================================
// THE ONE DETECTION FUNCTION
// =========================================================
async function tick(force = false) {
    console.log("[RAG] tick — scanning DOM...");

    // ---------- New-chat detection (runs every tick) ----------
    const currentUrl = location.href;
    if (currentUrl !== lastUrl) {
        console.log("[RAG] URL changed — new chat.");
        lastUrl = currentUrl;
        lastDetectedAnswer = "";
        lastUserPrompt = "";
        await notifyUIReset();
        return;
    }

    const hasMessages = domHasAnyMessages();
    if (domHadMessages && !hasMessages) {
        console.log("[RAG] DOM emptied — new chat.");
        lastDetectedAnswer = "";
        lastUserPrompt = "";
        await notifyUIReset();
        domHadMessages = false;
        return;
    }
    domHadMessages = hasMessages;

    // ---------- Prompt-change detection ----------
    const currentPrompt = getLatestUserPrompt();
    if (currentPrompt && currentPrompt !== lastUserPrompt) {
        console.log("[RAG] New prompt detected.");
        lastUserPrompt = currentPrompt;
        lastDetectedAnswer = "";

        // Show Waiting in the side panel until the new response arrives
        try {
            await chrome.runtime.sendMessage({
                type: "UI_RESET",
                answer: "",
                platform: "Waiting...",
                website: "",
                url: ""
            });
        } catch (_) {}
    }

    // ---------- Response detection ----------
    const answer = getLatestResponse();
    if (!answer) {
        console.log("[RAG] no response found");
        return;
    }
    if (!force && answer === lastDetectedAnswer) {
        console.log("[RAG] same as last, skipping");
        return;
    }

    lastDetectedAnswer = answer;
    console.log("[RAG] NEW response detected, length:", answer.length);

    await storeResponse(answer);
    await notifySidePanel(answer);
}

// =========================================================
// STREAMING-AWARE OBSERVER (fires detection ~1.5s after typing stops)
// =========================================================
function startStreamObserver() {
    if (observer) return;
    if (!document.body) { setTimeout(startStreamObserver, 500); return; }

    observer = new MutationObserver(() => {
        // Restart a short "quiet" countdown. When the DOM stops
        // changing for 1.5s, we assume the AI stopped typing and
        // fire detection.
        if (streamEndTimer) clearTimeout(streamEndTimer);
        streamEndTimer = setTimeout(() => {
            streamEndTimer = null;
            tick(true);
        }, 1500);
    });

    observer.observe(document.body, {
        childList: true,
        subtree: true,
        characterData: true
    });

    console.log("[RAG] Streaming observer started.");
}

// =========================================================
// START
// =========================================================
function start() {
    if (!document.body) { setTimeout(start, 500); return; }

    console.log("[RAG] starting 10-second scan loop");
    tick(false);
    tickTimer = setInterval(() => tick(false), 10000);

    startStreamObserver();
}

if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", start);
} else {
    start();
}

// =========================================================
// VISIBILITY / FOCUS (minimize → restore)
// =========================================================
document.addEventListener("visibilitychange", () => {
    if (document.hidden) return;
    console.log("[RAG] Tab visible — forcing detection.");
    // Re-check new-chat state on visibility change
    const hasMessages = domHasAnyMessages();
    if (domHadMessages && !hasMessages) {
        lastDetectedAnswer = "";
        lastUserPrompt = "";
        notifyUIReset();
    }
    domHadMessages = hasMessages;

    setTimeout(() => tick(true), 300);
});

window.addEventListener("focus", () => {
    if (document.hidden) return;
    console.log("[RAG] Window focus — forcing detection.");
    setTimeout(() => tick(true), 300);
});

// =========================================================
// MESSAGES FROM SIDE PANEL / BACKGROUND
// =========================================================
chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
    if (!message || !message.type) return false;

    // "Clear Response" button + alarm poll
    if (message.type === "FORCE_DETECT_LATEST_RESPONSE") {
        if (streamEndTimer) { clearTimeout(streamEndTimer); streamEndTimer = null; }
        lastDetectedAnswer = "";
        tick(true);
        sendResponse({ success: true });
        return true;
    }

    // "Analyze" button's soft reset, or "Clear Response" hard reset
    if (message.type === "RESET_DETECTION_STATE") {
        lastDetectedAnswer = "";
        lastUserPrompt = message.softReset === true ? lastUserPrompt : "";
        if (streamEndTimer) { clearTimeout(streamEndTimer); streamEndTimer = null; }
        sendResponse({ success: true });
        return true;
    }

    return false;
});

console.log("[RAG] content script ready!");