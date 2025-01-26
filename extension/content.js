console.log("Content script starting initialization...");

// Function to log WebSocket state
function getWebSocketState(ws) {
  const states = {
    0: 'CONNECTING',
    1: 'OPEN',
    2: 'CLOSING',
    3: 'CLOSED'
  };
  return states[ws.readyState] || 'UNKNOWN';
}

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
        // Process any queued messages
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
    console.log('sendMessage called, WebSocket state:', getWebSocketState(this.ws));
    if (this.ws.readyState === WebSocket.OPEN) {
      try {
        console.log('Preparing to send data:', {
          url: data.url,
          timestamp: data.timestamp,
          htmlLength: data.html.length
        });
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

console.log("Creating WebSocketClient instance...");
const wsClient = new WebSocketClient();

console.log("Setting up message listener...");
browser.runtime.onMessage.addListener((message, sender, sendResponse) => {
  console.log('Message received from background script:', message);

  if (message.type === "PING") {
    console.log('Received PING, responding...');
    return Promise.resolve({ status: "ready" });
  }

  if (message.type === "GET_PAGE_CONTENT") {
    console.log('Processing GET_PAGE_CONTENT message');
    const pageContent = {
      url: window.location.href,
      html: document.documentElement.outerHTML,
      timestamp: new Date().toISOString().replace(/\.\d{3}Z$/, 'Z')
    };

    console.log('Created page content object for:', pageContent.url);
    wsClient.sendMessage(pageContent);
  }

  return true;
});

// Send initial page content
console.log('Sending initial page content...');
const pageContent = {
  url: window.location.href,
  html: document.documentElement.outerHTML,
  timestamp: new Date().toISOString().replace(/\.\d{3}Z$/, 'Z')
};

wsClient.sendMessage(pageContent);

console.log("Content script initialization complete for:", window.location.href);