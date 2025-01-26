# Browser Recall

Browser Recall is a browser history and bookmark management system that captures, processes, and stores web page content in a searchable format. It consists of a browser extension and a FastAPI backend server that work together to provide the ability to search your the content of your browsing history and bookmarks.

## Features

- 🔍 Full-text search across browsing history and bookmarks
- 📝 Automatic conversion of web pages to markdown format
- 🔄 Real-time page content capture via WebSocket
- ⚡ Optimized SQLite database with FTS5 search
- 🛡️ Configurable domain exclusions
- 📊 Efficient content processing and storage

## System Architecture

### Backend Components

- **FastAPI Server**: Main application server handling WebSocket connections and HTTP endpoints
- **SQLite Database**: Stores history and bookmarks with full-text search capabilities
- **Page Reader**: Converts HTML content to markdown format
- **History Scheduler**: Background task for updating browser history
- **Configuration System**: Manages domain exclusions and reader settings

### Browser Extension

- **Content Script**: Captures page content and sends to backend
- **Background Script**: Manages WebSocket connection and message handling
- **Manifest**: Extension configuration and permissions

## Setup

### Prerequisites

- Python 3.8+
- Firefox Browser (for the extension)
- SQLite3

### Installation

1. Clone the repository:
```bash
git clone <repository-url>
cd browser-recall
```

2. Create and activate a virtual environment:
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

4. Install the browser extension:
   - Open Firefox
   - Navigate to `about:debugging`
   - Click "This Firefox"
   - Click "Load Temporary Add-on"
   - Select the `manifest.json` file from the `extension` directory

### Configuration

1. Configure domain exclusions in `app/config.yaml`:
```yaml
ignored_domains:
  - "localhost"
  - "127.0.0.1"
  - "*.local"
  # Add more patterns as needed
```

2. Configure the server port in `main.py` (default: 8523)

## Usage

1. Start the server:
```bash
python main.py
```

2. The extension will automatically:
   - Capture page content as you browse
   - Send content to the backend server
   - Update history and bookmarks

3. Access the API endpoints:
   - Search history: `GET /history/search`
   - Search bookmarks: `GET /bookmarks/search`
   - Advanced search: `GET /history/search/advanced`
   - Manage ignored domains: `GET/POST/DELETE /config/ignored-domains`

## API Documentation

### History Endpoints

- `GET /history/search`
  - Query parameters:
    - `domain`: Filter by domain
    - `start_date`: Filter by start date
    - `end_date`: Filter by end date
    - `search_term`: Full-text search
    - `include_content`: Include markdown content

- `GET /history/search/advanced`
  - Advanced full-text search using SQLite FTS5 syntax

### Bookmark Endpoints

- `GET /bookmarks/search`
  - Query parameters:
    - `domain`: Filter by domain
    - `folder`: Filter by folder
    - `search_term`: Search in titles

### Configuration Endpoints

- `GET /config/ignored-domains`: List ignored domains
- `POST /config/ignored-domains`: Add domain pattern
- `DELETE /config/ignored-domains/{pattern}`: Remove domain pattern

## Development

- Logs are stored in the `logs` directory
- Database file: `browser_history.db`
- WebSocket endpoint: `ws://localhost:8523/ws`