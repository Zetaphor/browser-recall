console.log("Background script loaded");

async function isContentScriptReady(tabId) {
  try {
    await browser.tabs.sendMessage(tabId, { type: "PING" });
    return true;
  } catch (error) {
    return false;
  }
}

async function waitForContentScript(tabId, maxAttempts = 10) {
  console.log(`Waiting for content script in tab ${tabId}`);
  for (let i = 0; i < maxAttempts; i++) {
    if (await isContentScriptReady(tabId)) {
      console.log(`Content script ready in tab ${tabId}`);
      return true;
    }
    console.log(`Attempt ${i + 1}: Content script not ready, waiting...`);
    await new Promise(resolve => setTimeout(resolve, 500));
  }
  console.log(`Content script not ready after ${maxAttempts} attempts`);
  return false;
}

async function sendMessageToTab(tabId) {
  try {
    console.log(`Checking content script status for tab ${tabId}`);
    if (await waitForContentScript(tabId)) {
      console.log(`Sending GET_PAGE_CONTENT message to tab ${tabId}`);
      await browser.tabs.sendMessage(tabId, {
        type: "GET_PAGE_CONTENT"
      });
      console.log(`Successfully sent message to tab ${tabId}`);
    }
  } catch (error) {
    console.error(`Error sending message to tab ${tabId}:`, error);
  }
}

browser.webNavigation.onCompleted.addListener(async (details) => {
  console.log("Navigation completed", details);
  if (details.frameId === 0) { // Only handle main frame navigation
    console.log(`Main frame navigation detected for tab ${details.tabId}`);
    await sendMessageToTab(details.tabId);
  }
});