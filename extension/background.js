console.log("Background script loaded");

class WebSocketClient {
  constructor() {
    console.log("WebSocketClient constructor called");
    this.messageQueue = [];
    this.connect();
    this.reconnectAttempts = 0;
    this.maxReconnectAttempts = 5;
  }

  connect() {
    console.log('Attempting to connect to WebSocket server...');
    try {
      this.ws = new WebSocket('ws://localhost:8523/ws');
      console.log('WebSocket instance created');

      this.ws.addEventListener('open', () => {
        console.log('WebSocket connection opened successfully');
        this.reconnectAttempts = 0;
        this.processQueue();
      });

      this.ws.addEventListener('error', (event) => {
        console.error('WebSocket error occurred:', event);
      });

      this.ws.addEventListener('close', (event) => {
        console.log('WebSocket connection closed:', event.code, event.reason);
        this.tryReconnect();
      });

      this.ws.addEventListener('message', (event) => {
        console.log('Received message from server:', event.data);
      });
    } catch (error) {
      console.error('Error creating WebSocket:', error);
    }
  }

  processQueue() {
    console.log(`Processing message queue (${this.messageQueue.length} messages)`);
    while (this.messageQueue.length > 0) {
      const data = this.messageQueue.shift();
      this.sendMessage(data);
    }
  }

  tryReconnect() {
    if (this.reconnectAttempts < this.maxReconnectAttempts) {
      this.reconnectAttempts++;
      console.log(`Attempting to reconnect (${this.reconnectAttempts}/${this.maxReconnectAttempts})...`);
      setTimeout(() => this.connect(), 2000 * this.reconnectAttempts);
    } else {
      console.log('Max reconnection attempts reached');
    }
  }

  sendMessage(data) {
    if (this.ws.readyState === WebSocket.OPEN) {
      try {
        console.log('Sending data for URL:', data.url);
        this.ws.send(JSON.stringify(data));
        console.log('Data sent successfully');
        return true;
      } catch (error) {
        console.error('Error sending data:', error);
        return false;
      }
    } else {
      console.log('WebSocket not ready, queueing message');
      this.messageQueue.push(data);
      return true;
    }
  }
}

const wsClient = new WebSocketClient();

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

// Listen for messages from content scripts
browser.runtime.onMessage.addListener((message, sender) => {
  if (message.type === "SEND_PAGE_CONTENT") {
    console.log('Received page content from tab:', sender.tab.id);
    wsClient.sendMessage(message.data);
  }
});

browser.webNavigation.onCompleted.addListener(async (details) => {
  console.log("Navigation completed", details);
  if (details.frameId === 0) {
    console.log(`Main frame navigation detected for tab ${details.tabId}`);
    await sendMessageToTab(details.tabId);
  }
});