// =========================================================
// ADAPTIVE RAG - BACKGROUND SERVICE WORKER
// =========================================================

const BACKEND_URL = "http://127.0.0.1:8000/analyze";

const DEFAULT_SETTINGS = {
    autoAnalyze: false,
    textSize: 14,
    uiScale: 100,
    confidenceThreshold: 70,
    maxSources: 6
};

// =========================================================
// INSTALL / STARTUP
// =========================================================
chrome.runtime.onInstalled.addListener(async () => {
    try {
        const data = await chrome.storage.local.get(["settings", "analysisHistory"]);
        const updates = {};
        if (!data.settings) updates.settings = DEFAULT_SETTINGS;
        if (!data.analysisHistory) updates.analysisHistory = [];
        if (Object.keys(updates).length > 0) {
            await chrome.storage.local.set(updates);
        }
        console.log("Adaptive RAG installed.");
        chrome.alarms.create("keepAlive", { periodInMinutes: 0.4 });
    } catch (error) {
        console.error("Installation error:", error);
    }
});

chrome.runtime.onStartup.addListener(() => {
    chrome.alarms.create("keepAlive", { periodInMinutes: 0.4 });
});

// =========================================================
// ALARM HANDLER (Feature 6 - works when minimized)
// =========================================================
chrome.alarms.onAlarm.addListener(async (alarm) => {
    if (alarm.name !== "keepAlive") return;

    try {
        const tabs = await chrome.tabs.query({
            url: [
                "https://chatgpt.com/*",
                "https://chat.openai.com/*",
                "https://gemini.google.com/*",
                "https://claude.ai/*",
                "https://copilot.microsoft.com/*"
            ]
        });

        for (const tab of tabs) {
            if (!tab.id) continue;

            // Skip hidden tabs — their content script timers are
            // throttled anyway, and the visibility handler will
            // catch up when the user returns.
            if (tab.active === false && tab.windowId) {
                try {
                    const win = await chrome.windows.get(tab.windowId);
                    if (!win.focused) {
                        continue;
                    }
                } catch (_) {}
            }

            try {
                await chrome.tabs.sendMessage(tab.id, {
                    type: "FORCE_DETECT_LATEST_RESPONSE"
                }).catch(() => {});
            } catch (_) {}
        }
    } catch (error) {
        console.log("Alarm poll error:", error);
    }
});

// =========================================================
// SIDE PANEL CONFIG
// =========================================================
chrome.sidePanel.setPanelBehavior({
    openPanelOnActionClick: true
}).catch((error) => {
    console.error("Side panel configuration error:", error);
});

// =========================================================
// MESSAGE HANDLER
// =========================================================
chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
    if (!message || !message.type) return;

    handleMessage(message)
        .then((result) => sendResponse(result || { success: true }))
        .catch((error) => {
            console.error("Message handling error:", error);
            sendResponse({ success: false, error: error.message || "Message handling failed." });
        });

    return true;
});

// =========================================================
// MESSAGE ROUTER
// =========================================================
async function handleMessage(message) {
    switch (message.type) {

        case "AI_RESPONSE_DETECTED":
            return await handleAIResponse(message);

        case "UI_RESET":
        // Only forward the reset to the side panel — DO NOT touch storage.
        await sendRuntimeMessage({
            type: "UI_RESET",
            answer: "", platform: "Waiting...", website: "", url: ""
        });
        return { success: true };

        case "MANUAL_ANALYZE":
            return await analyzeResponse(
                message.answer,
                message.platform,
                message.website,
                message.url
            );

        case "GET_LATEST_DATA":
            return await getLatestData();

        case "CLEAR_HISTORY":
            return await clearHistory();

        case "CLEAR_LATEST_RESPONSE":
            return await clearLatestResponse();

        case "RESET_DETECTION_STATE":
            try {
                const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
                if (tab && tab.id) {
                    await chrome.tabs.sendMessage(tab.id, {
                        type: "RESET_DETECTION_STATE",
                        softReset: message.softReset === true
                    }).catch(() => {});
                }
                return { success: true };
            } catch (error) {
                return { success: false, error: error.message };
            }

        default:
            return { success: false, error: `Unknown message type: ${message.type}` };
    }
}

// =========================================================
// HANDLE DETECTED AI RESPONSE (Feature 6)
// Preserves latestResult when the same answer is re-detected.
// =========================================================
async function handleAIResponse(message) {
    try {
        const answer = String(message.answer || "").trim();
        if (!answer || answer.length < 10) {
            return { success: false, error: "Detected answer is too short." };
        }

        const platform = message.platform || "AI";
        const website = message.website || "";
        const url = message.url || "";

        const existing = await chrome.storage.local.get(["latestAnswer", "latestResult"]);
        const existingAnswer = existing.latestAnswer || "";
        const isSameAnswer = (existingAnswer === answer);

        if (isSameAnswer) {
            // Same response re-detected → keep existing result.
            await chrome.storage.local.set({
                platform, sourceWebsite: website, sourceURL: url,
                detectedAt: new Date().toISOString()
            });
            return { success: true, message: "Same response — result preserved." };
        }

        // New response → clear the old analysis result
        await chrome.storage.local.set({
            latestAnswer: answer,
            latestResult: null,
            platform, sourceWebsite: website, sourceURL: url,
            detectedAt: new Date().toISOString()
        });

        await sendRuntimeMessage({
            type: "NEW_AI_RESPONSE",
            answer, platform, website, url
        });

        return { success: true, message: "AI response detected." };
    } catch (error) {
        return { success: false, error: error.message };
    }
}

// =========================================================
// GET LATEST DATA
// =========================================================
async function getLatestData() {
    const data = await chrome.storage.local.get([
        "latestAnswer", "latestResult", "platform",
        "sourceWebsite", "sourceURL", "detectedAt", "analysisHistory"
    ]);

    return {
        success: true,
        data: {
            latestAnswer: data.latestAnswer || "",
            latestResult: data.latestResult || null,
            platform: data.platform || "",
            sourceWebsite: data.sourceWebsite || "",
            sourceURL: data.sourceURL || "",
            detectedAt: data.detectedAt || "",
            analysisHistory: data.analysisHistory || []
        }
    };
}

// =========================================================
// CLEAR LATEST RESPONSE
// =========================================================
async function clearLatestResponse() {
    await chrome.storage.local.remove([
        "latestAnswer", "latestResult", "platform",
        "sourceWebsite", "sourceURL", "detectedAt"
    ]);
    await sendRuntimeMessage({ type: "LATEST_RESPONSE_CLEARED" });
    return { success: true };
}

// =========================================================
// CLEAR HISTORY
// =========================================================
async function clearHistory() {
    await chrome.storage.local.set({ analysisHistory: [] });
    await sendRuntimeMessage({ type: "HISTORY_CLEARED" });
    return { success: true };
}

// =========================================================
// MANUAL ANALYSIS
// =========================================================
async function analyzeResponse(answer, platform = "AI", website = "", url = "") {
    try {
        const cleanAnswer = String(answer || "").trim();
        if (!cleanAnswer || cleanAnswer.length < 10) {
            await sendRuntimeMessage({
                type: "ANALYSIS_ERROR",
                error: "Please enter a valid response with at least 10 characters."
            });
            return { success: false, error: "Answer is too short." };
        }

        await sendRuntimeMessage({ type: "ANALYSIS_STARTED", platform });

        const response = await fetch(BACKEND_URL, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                answer: cleanAnswer, platform, website, url
            })
        });

        if (!response.ok) {
            let errorMessage = `Backend returned status ${response.status}`;
            try {
                const errorData = await response.json();
                if (errorData && errorData.detail) errorMessage = String(errorData.detail);
            } catch (_) {}
            throw new Error(errorMessage);
        }

        const result = await response.json();
        await chrome.storage.local.set({ latestResult: result });

        const data = await chrome.storage.local.get(["analysisHistory"]);
        const history = Array.isArray(data.analysisHistory) ? data.analysisHistory : [];

        history.unshift({
            id: "analysis_" + Date.now(),
            timestamp: new Date().toISOString(),
            platform, website, url,
            answer: cleanAnswer,
            result: result
        });

        await chrome.storage.local.set({ analysisHistory: history.slice(0, 50) });

        await sendRuntimeMessage({
            type: "ANALYSIS_COMPLETE", result, platform
        });

        return { success: true, result };
    } catch (error) {
        await sendRuntimeMessage({
            type: "ANALYSIS_ERROR",
            error: error.message || "Analysis failed."
        });
        return { success: false, error: error.message || "Analysis failed." };
    }
}

// =========================================================
// SAFE RUNTIME MESSAGE SENDER
// =========================================================
async function sendRuntimeMessage(message) {
    try {
        await chrome.runtime.sendMessage(message);
    } catch (error) {
        console.log("Runtime message could not be delivered:", message.type);
    }
}

console.log("Adaptive RAG background service worker loaded.");