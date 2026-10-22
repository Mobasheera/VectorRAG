// =========================================================
// ELEMENTS
// =========================================================
const platformElement = document.getElementById("platform");
const responseElement = document.getElementById("response");
const statusElement = document.getElementById("status");
const analyzeButton = document.getElementById("analyzeBtn");
const clearResponseButton = document.getElementById("clearResponse");
const scoreElement = document.getElementById("score");
const scoreFill = document.getElementById("scoreFill");
const scoreLabel = document.getElementById("scoreLabel");
const claimsElement = document.getElementById("claims");
const sourcesElement = document.getElementById("sources");
const historyElement = document.getElementById("history");
const clearHistoryButton = document.getElementById("clearHistory");
const manualInput = document.getElementById("manualInput");

let currentAnswer = "";
let currentPlatform = "";
let currentWebsite = "";
let currentURL = "";
let isAnalyzing = false;
let lastProcessedAnswer = "";

// =========================================================
// RESET CONTENT SCRIPT STATE
// =========================================================
async function resetContentScriptState(softReset = false) {
    try {
        const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
        if (tab && tab.id) {
            await chrome.tabs.sendMessage(tab.id, {
                type: "RESET_DETECTION_STATE",
                softReset: softReset
            }).catch(() => {});
        }
    } catch (error) {
        console.log("Could not reset content script:", error);
    }
}

// =========================================================
// LOAD DATA (Features 5 & 6)
// =========================================================
async function loadData() {
    try {
        const data = await chrome.storage.local.get([
            "analysisHistory",
            "latestAnswer",
            "latestResult",
            "platform",
            "sourceWebsite",
            "sourceURL"
        ]);

        // ---- Restore detected response ----
        if (data.latestAnswer && data.latestAnswer.trim().length > 0) {
            currentAnswer = data.latestAnswer;
            currentPlatform = data.platform || "AI";
            currentWebsite = data.sourceWebsite || "";
            currentURL = data.sourceURL || "";

            platformElement.textContent = currentPlatform;
            responseElement.textContent =
                currentAnswer.substring(0, 500) +
                (currentAnswer.length > 500 ? "..." : "");

            statusElement.classList.add("active");
            analyzeButton.disabled = false;
            lastProcessedAnswer = currentAnswer;
        } else {
            // No stored answer → Waiting state (Feature 5)
            currentAnswer = "";
            currentPlatform = "";
            currentWebsite = "";
            currentURL = "";
            lastProcessedAnswer = "";

            responseElement.textContent = "Waiting for an AI response...";
            platformElement.textContent = "Waiting...";
            statusElement.classList.remove("active");
            analyzeButton.disabled = true;
        }

        // ---- Restore analysis result (Feature 6) ----
        if (data.latestResult) {
            console.log("Restoring last analysis result.");
            renderResult(data.latestResult);
        } else {
            clearResults();
        }

        renderHistory(data.analysisHistory || []);

        // If no stored answer, ask content script to detect the DOM now
        if (!data.latestAnswer || data.latestAnswer.trim().length === 0) {
            await getResponseFromActiveTab();
        }

    } catch (error) {
        console.error("Load data error:", error);
    }
}

// =========================================================
// GET RESPONSE FROM ACTIVE TAB (used by Clear Response, Manual, etc.)
// =========================================================
async function getResponseFromActiveTab() {
    try {
        const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
        if (!tab || !tab.id) return;

        const results = await chrome.scripting.executeScript({
            target: { tabId: tab.id },
            func: () => {
                const selectors = [
                    '[data-message-author-role="assistant"]',
                    '[data-message-author-role="model"]',
                    '.model-response-text',
                    '.markdown', '.prose', '.response-content',
                    '[class*="assistant"]', '[class*="response"]'
                ];
                for (const selector of selectors) {
                    const elements = document.querySelectorAll(selector);
                    if (!elements.length) continue;

                    const element = elements[elements.length - 1];
                    const text = (element.innerText || element.textContent || "")
                        .replace(/\s+/g, " ").trim();
                    if (text.length < 20) continue;

                    const hostname = window.location.hostname;
                    let platform = "AI";
                    if (hostname.includes("chatgpt") || hostname.includes("openai")) platform = "ChatGPT";
                    else if (hostname.includes("gemini")) platform = "Gemini";
                    else if (hostname.includes("claude")) platform = "Claude";
                    else if (hostname.includes("copilot")) platform = "Copilot";
                    else if (hostname.includes("perplexity")) platform = "Perplexity";

                    return { answer: text, platform, website: hostname, url: window.location.href };
                }
                return null;
            }
        });

        const detected = results && results[0] && results[0].result;
        if (!detected || !detected.answer) return;

        showResponse(detected.answer, detected.platform, detected.website, detected.url);
        lastProcessedAnswer = detected.answer;
    } catch (error) {
        console.error("Error getting response from active tab:", error);
    }
}

// =========================================================
// SHOW RESPONSE
// =========================================================
function showResponse(answer, aiPlatform, website = "", url = "") {
    if (!answer || !answer.trim()) return;

    currentAnswer = answer.trim();
    currentPlatform = aiPlatform || "AI";
    currentWebsite = website || "";
    currentURL = url || "";

    platformElement.textContent = currentPlatform;
    responseElement.textContent =
        currentAnswer.substring(0, 500) +
        (currentAnswer.length > 500 ? "..." : "");

    statusElement.classList.add("active");
    analyzeButton.disabled = false;
    if (clearResponseButton) clearResponseButton.disabled = false;

    // NOTE: do NOT clearResults here — that would wipe restored analysis
}

// =========================================================
// CLEAR RESULTS (only visual score/claims/sources)
// =========================================================
function clearResults() {
    scoreElement.textContent = "--";
    scoreLabel.textContent = "Waiting";
    scoreFill.style.width = "0%";
    claimsElement.innerHTML = `<div class="empty">Claims will appear after analysis.</div>`;
    sourcesElement.innerHTML = `<div class="empty">Verification sources will appear here.</div>`;
    document.getElementById("claimCount").textContent = "0";
    document.getElementById("sourceCount").textContent = "0";
}

// =========================================================
// ANALYZE BUTTON (Feature 4)
// =========================================================
analyzeButton.addEventListener("click", async () => {
    if (isAnalyzing) return;

    const manualText = manualInput ? manualInput.value.trim() : "";

    let answerToAnalyze = "";
    let platformToAnalyze = "";
    let websiteToAnalyze = "";
    let urlToAnalyze = "";
    let analysisSource = "automatic";

    // Feature 4: Manual box takes strict priority
    if (manualText.length > 10) {
        answerToAnalyze = manualText;
        platformToAnalyze = "Manual";
        websiteToAnalyze = "manual";
        urlToAnalyze = "";
        analysisSource = "manual";

        currentAnswer = answerToAnalyze;
        currentPlatform = platformToAnalyze;
        currentWebsite = websiteToAnalyze;
        currentURL = urlToAnalyze;

        manualInput.value = "";
        showResponse(answerToAnalyze, platformToAnalyze, websiteToAnalyze, urlToAnalyze);
    } else {
        if (!currentAnswer || currentAnswer.length < 10) {
            await getResponseFromActiveTab();
        }
        answerToAnalyze = currentAnswer;
        platformToAnalyze = currentPlatform || "AI";
        websiteToAnalyze = currentWebsite || "";
        urlToAnalyze = currentURL || "";
    }

    if (!answerToAnalyze || answerToAnalyze.length < 10) {
        alert("No AI response detected.\n\nAsk a question and wait for the AI response, or paste a response manually.");
        return;
    }

    isAnalyzing = true;
    analyzeButton.disabled = true;
    analyzeButton.textContent = "⏳ Analyzing...";

    clearResults();
    claimsElement.innerHTML = `<div class="empty">Analyzing claims...</div>`;
    sourcesElement.innerHTML = `<div class="empty">Searching trusted sources...</div>`;

    try {
        const response = await fetch("http://127.0.0.1:8000/analyze", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                answer: answerToAnalyze,
                platform: platformToAnalyze,
                website: websiteToAnalyze || window.location.hostname || "unknown",
                url: urlToAnalyze || window.location.href || ""
            })
        });

        if (!response.ok) {
            const errorText = await response.text();
            throw new Error(`Backend error (${response.status}): ${errorText}`);
        }

        const result = await response.json();

        const data = await chrome.storage.local.get(["analysisHistory"]);
        const history = data.analysisHistory || [];

        history.unshift({
            id: "analysis_" + Date.now(),
            timestamp: new Date().toISOString(),
            platform: platformToAnalyze,
            website: websiteToAnalyze || window.location.hostname || "unknown",
            url: urlToAnalyze || window.location.href || "",
            answer: answerToAnalyze,
            result: result,
            source: analysisSource
        });

        const limitedHistory = history.slice(0, 50);

        // Persist the answer too, so restoring works
        await chrome.storage.local.set({
            analysisHistory: limitedHistory,
            latestAnswer: answerToAnalyze,
            latestResult: result,
            platform: platformToAnalyze,
            sourceWebsite: websiteToAnalyze,
            sourceURL: urlToAnalyze,
            _lastUpdate: Date.now()
        });

        renderResult(result);
        renderHistory(limitedHistory.slice(0, 10));

    } catch (error) {
        console.error("Analysis error:", error);
        scoreElement.textContent = "❌";
        scoreLabel.textContent = "Error";
        claimsElement.innerHTML = `<div class="empty">Error: ${escapeHTML(error.message)}</div>`;
        sourcesElement.innerHTML = `<div class="empty">Make sure the backend is running at http://127.0.0.1:8000</div>`;
    } finally {
        isAnalyzing = false;
        analyzeButton.disabled = false;
        analyzeButton.textContent = "✦ Analyze Response";
        // Feature 3: do NOT reset content script detection here.
        // The 10-second periodic loop in content.js will resume.
    }
});

// =========================================================
// CLEAR RESPONSE (Features 2 & 5)
// Clears UI, then after 10s asks content script to re-detect.
// =========================================================
if (clearResponseButton) {
    clearResponseButton.addEventListener("click", async () => {
        currentAnswer = "";
        currentPlatform = "";
        currentWebsite = "";
        currentURL = "";
        lastProcessedAnswer = "";

        responseElement.textContent = "Waiting for an AI response...";
        platformElement.textContent = "Waiting...";
        statusElement.classList.remove("active");
        analyzeButton.disabled = true;

        clearResults();

        try {
            await chrome.storage.local.remove([
                "latestAnswer", "latestResult", "platform",
                "sourceWebsite", "sourceURL", "_lastUpdate"
            ]);
        } catch (error) {
            console.error("Clear response storage error:", error);
        }

        // Tell content script to re-arm its detection
        await resetContentScriptState(false);

        // Feature 2: 10 seconds later, re-read from the DOM
        setTimeout(async () => {
            await getResponseFromActiveTab();
            // Also nudge the content script to look again
            try {
                const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
                if (tab && tab.id) {
                    chrome.tabs.sendMessage(tab.id, {
                        type: "FORCE_DETECT_LATEST_RESPONSE"
                    }).catch(() => {});
                }
            } catch (_) {}
        }, 10000);
    });
}

// =========================================================
// RENDER RESULT
// =========================================================
function renderResult(result) {
    if (!result) return;

    let reliability = result.reliability;
    if (reliability === undefined || reliability === null) {
        if (result.claims && result.claims.length > 0) {
            let supported = 0, partial = 0;
            result.claims.forEach(claim => {
                const status = String(claim.status || "").toUpperCase();
                if (status === "SUPPORTED") supported++;
                else if (status === "PARTIALLY SUPPORTED") partial++;
            });
            reliability = ((supported + partial * 0.5) / result.claims.length) * 100;
        } else {
            reliability = 0;
        }
    }
    reliability = Math.max(0, Math.min(100, Number(reliability)));

    scoreElement.textContent = Math.round(reliability) + "%";
    scoreFill.style.width = reliability + "%";
    scoreFill.style.transition = "width 0.8s ease";

    if (reliability >= 80) scoreLabel.textContent = "HIGHLY RELIABLE ✅";
    else if (reliability >= 60) scoreLabel.textContent = "MODERATELY RELIABLE ⚠️";
    else if (reliability >= 40) scoreLabel.textContent = "LOW RELIABILITY ⚠️";
    else scoreLabel.textContent = "VERY LOW RELIABILITY ❌";

    renderClaims(result.claims || []);
    renderSources(result.sources || []);
}

// =========================================================
// RENDER CLAIMS
// =========================================================
function renderClaims(data) {
    if (!Array.isArray(data)) data = [];
    document.getElementById("claimCount").textContent = data.length;

    if (!data.length) {
        claimsElement.innerHTML = `<div class="empty">No claims extracted from the response.</div>`;
        return;
    }

    let html = "";
    data.forEach((claim) => {
        const status = String(claim.status || claim.verdict || "UNCERTAIN").toUpperCase();
        let cssClass = "uncertain", icon = "❓", statusText = "Uncertain";

        if (status === "SUPPORTED") { cssClass = "supported"; icon = "✅"; statusText = "Supported"; }
        else if (status === "CONTRADICTED") { cssClass = "hallucination"; icon = "❌"; statusText = "Hallucination"; }
        else if (status === "PARTIALLY SUPPORTED") { cssClass = "uncertain"; icon = "⚠️"; statusText = "Partial"; }
        else if (status === "INSUFFICIENT EVIDENCE") { cssClass = "uncertain"; icon = "❓"; statusText = "Insufficient"; }
        else if (status === "ERROR") { cssClass = "hallucination"; icon = "💥"; statusText = "Error"; }

        let confidence = claim.confidence;
        if (confidence === undefined || confidence === null) {
            confidence = claim.similarity_score;
            if (confidence !== undefined && confidence !== null) confidence = Math.round(confidence * 100);
        }
        if (confidence === undefined || confidence === null) confidence = claim.score;
        if (confidence === undefined || confidence === null) confidence = "--";
        else confidence = Math.round(confidence);

        const claimText = claim.claim || claim.text || claim.statement || "Unknown claim";
        const complexity = claim.complexity || "";

        html += `
            <div class="claim">
                <div class="claim-top">
                    <div class="claim-status ${cssClass}">
                        ${icon} ${statusText}
                        ${complexity ? `<span style="font-weight:normal;font-size:8px;color:#777;"> (${complexity})</span>` : ""}
                    </div>
                    <div class="claim-score">${confidence}%</div>
                </div>
                <div class="claim-text">${escapeHTML(claimText)}</div>
            </div>
        `;
    });

    claimsElement.innerHTML = html;
}

// =========================================================
// RENDER SOURCES
// =========================================================
function renderSources(data) {
    if (!Array.isArray(data)) data = [];
    document.getElementById("sourceCount").textContent = data.length;

    if (!data.length) {
        sourcesElement.innerHTML = `<div class="empty">No trusted sources found.</div>`;
        return;
    }

    data = data.slice(0, 15);
    let html = "";

    data.forEach(source => {
        const url = source.url || source.link || "#";
        const title = source.title || source.name || "Source";
        const trustLevel = source.trust_level || "unknown";
        const snippet = source.snippet || "";
        let trustIcon = "🔵";
        if (trustLevel === "very_high") trustIcon = "🟢";
        else if (trustLevel === "high") trustIcon = "🟢";
        else if (trustLevel === "medium") trustIcon = "🟡";
        else if (trustLevel === "reference") trustIcon = "🔵";

        html += `
            <a class="source" href="${escapeHTML(url)}" target="_blank" rel="noopener noreferrer">
                <div class="source-title">${trustIcon} ${escapeHTML(title)}</div>
                <div class="source-url">${escapeHTML(url)}</div>
                ${snippet ? `<div style="font-size:7px;color:#666;margin-top:4px;">${escapeHTML(snippet.substring(0, 80))}...</div>` : ""}
            </a>
        `;
    });

    sourcesElement.innerHTML = html;
}

// =========================================================
// HISTORY
// =========================================================
async function loadHistory() {
    try {
        const data = await chrome.storage.local.get(["analysisHistory"]);
        renderHistory(data.analysisHistory || []);
    } catch (error) {
        console.error("Load history error:", error);
    }
}

function renderHistory(data) {
    if (!Array.isArray(data) || !data.length) {
        historyElement.innerHTML = `<div class="empty">No previous analyses.</div>`;
        return;
    }

    let html = "";
    data.slice(0, 10).forEach(item => {
        const reliability = item.result?.reliability ?? item.result?.score ?? "--";
        const answer = (item.answer || "").substring(0, 80);
        const platform = item.platform || "AI";

        html += `
            <div class="history-item">
                <div class="history-icon">◈</div>
                <div class="history-info">
                    <div class="history-platform">${escapeHTML(platform)}</div>
                    <div class="history-answer">${escapeHTML(answer)}${answer.length >= 80 ? "..." : ""}</div>
                </div>
                <div class="history-score">${reliability}%</div>
            </div>
        `;
    });

    historyElement.innerHTML = html;
}

// =========================================================
// CLEAR HISTORY
// =========================================================
clearHistoryButton.addEventListener("click", async () => {
    await chrome.storage.local.set({ analysisHistory: [] });
    loadHistory();
});

// =========================================================
// ESCAPE HTML
// =========================================================
function escapeHTML(text) {
    const div = document.createElement("div");
    div.textContent = String(text || "");
    return div.innerHTML;
}

// =========================================================
// RUNTIME MESSAGE LISTENER
// =========================================================
chrome.runtime.onMessage.addListener((message) => {
    if (!message || !message.type) return;

    // Handle explicit UI reset from content script (new chat)
    if (message.type === "UI_RESET") {
        console.log("Sidepanel: UI_RESET received. Clearing current response.");

        currentAnswer = "";
        currentPlatform = "";
        currentWebsite = "";
        currentURL = "";
        lastProcessedAnswer = "";

        responseElement.textContent = "Waiting for an AI response...";
        platformElement.textContent = "Waiting...";
        statusElement.classList.remove("active");
        analyzeButton.disabled = true;

        clearResults();
        return;
    }
    
    // Feature 4: ignore incoming responses while analyzing
    if (message.type === "NEW_AI_RESPONSE") {
        if (isAnalyzing) return;

        const answer = message.answer || "";

        if (!answer.trim()) {
            // Waiting state
            currentAnswer = "";
            currentPlatform = "";
            responseElement.textContent = "Waiting for an AI response...";
            platformElement.textContent = "Waiting...";
            statusElement.classList.remove("active");
            analyzeButton.disabled = true;
            clearResults();
            return;
        }

        showResponse(
            answer,
            message.platform || "AI",
            message.website || "",
            message.url || ""
        );
        lastProcessedAnswer = answer;
    }

    if (message.type === "ANALYSIS_COMPLETE") {
        if (message.result) renderResult(message.result);
    }

    if (message.type === "ANALYSIS_ERROR") {
        scoreElement.textContent = "❌";
        scoreLabel.textContent = "Error";
        claimsElement.innerHTML = `<div class="empty">${escapeHTML(message.error || "Analysis failed")}</div>`;
    }

    if (message.type === "HISTORY_CLEARED") {
        renderHistory([]);
    }
});

// =========================================================
// INITIAL LOAD
// =========================================================
document.addEventListener("DOMContentLoaded", async () => {
    await loadData();
    console.log("Sidepanel loaded!");
});

// =========================================================
// VISIBILITY CHANGE (Feature 6 - keep result on restore)
// =========================================================
document.addEventListener("visibilitychange", () => {
    if (!document.hidden) {
        loadData();
    }
});