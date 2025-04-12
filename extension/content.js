console.log("Content script starting initialization...");

function sendPageContent() {
  const pageContent = {
    url: window.location.href,
    timestamp: new Date().toISOString().replace(/\.\d{3}Z$/, 'Z')
  };

  browser.runtime.sendMessage({
    type: "SEND_PAGE_URL",
    data: pageContent
  });
}

// Listen for messages from the background script
browser.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message.type === "PING") {
    return Promise.resolve({ status: "ready" });
  }

  return true;
});

// Send initial page content
sendPageContent();

console.log("Content script initialization complete for:", window.location.href);