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
    console.log(`Attempting to reconnect (${this.reconnectAttempts}/${this.maxReconnectAttempts})...`);
    setTimeout(() => this.connect(), 2000 * this.reconnectAttempts);
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

// Listen for messages from content scripts
browser.runtime.onMessage.addListener((message, sender) => {
  if (message.type === "SEND_PAGE_URL") {
    console.log('Received page url from tab:', sender.tab.id);
    wsClient.sendMessage(message.data);
  }
});