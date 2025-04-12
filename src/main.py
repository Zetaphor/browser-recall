from fastapi import FastAPI, WebSocket
from starlette.websockets import WebSocketDisconnect
import uvicorn
from logger import Logger
import os
from database import Database
from crawl4ai import AsyncWebCrawler
from domain_exclusions import DomainExclusions
from base_crawler import BaseCrawler
import asyncio
from contextlib import asynccontextmanager
from browser_history import get_history
from dotenv import load_dotenv
# Create logs directory if it doesn't exist
os.makedirs('logs', exist_ok=True)

# Load environment variables
load_dotenv()
CRAWL_INTERVAL = int(os.getenv('CRAWL_INTERVAL', 30))  # Default to 30 seconds if not set

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    global history_crawler
    logger.info("Initializing crawler and loading browser history...")
    try:
        # Initialize history crawler
        history_crawler = HistoryCrawler(db, domain_exclusions, logger)
        async with history_crawler:  # Use async context manager
            outputs = get_history()
            history_crawler.crawl_queue = outputs.histories
            logger.info(f"Loaded {len(history_crawler.crawl_queue)} URLs from browser history")

            # Start the crawler in the background
            task = asyncio.create_task(history_crawler.start_crawler())
            yield
            # Stop the crawler
            history_crawler.is_running = False
            await task  # Wait for crawler to finish

    except Exception as e:
        logger.error(f"Error during startup: {str(e)}")
        yield

app = FastAPI(lifespan=lifespan)
logger = Logger()

db = Database()
domain_exclusions = DomainExclusions()

class HistoryCrawler(BaseCrawler):
    def __init__(self, db: Database, domain_exclusions: DomainExclusions, logger: Logger):
        super().__init__(db, domain_exclusions, logger)
        self.crawl_queue = []
        self.is_running = True

    async def start_crawler(self):
        while self.is_running and self.crawl_queue:
            timestamp, url, title = self.crawl_queue.pop(0)

            should_skip, skip_reason = self.should_skip_url(url)
            if should_skip:
                self.logger.info(f"Skipping URL from history: {url} ({skip_reason})")
                continue

            success, result = await self.crawl_url(url, title)
            if success:
                self.logger.info(f"Processed historical URL: {url}")

            await asyncio.sleep(CRAWL_INTERVAL)  # Use environment variable for interval

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    logger.info("New WebSocket connection established")

    ws_crawler = BaseCrawler(db, domain_exclusions, logger)

    try:
        while True:
            data = await websocket.receive_json()
            url = data["url"]

            should_skip, skip_reason = ws_crawler.should_skip_url(url)
            if should_skip:
                logger.info(f"Skipping URL: {url} ({skip_reason})")
                await websocket.send_json({
                    "status": "skipped",
                    "data": {
                        "url": url,
                        "title": skip_reason,
                        "timestamp": data["timestamp"]
                    }
                })
                continue

            success, result = await ws_crawler.crawl_url(url)
            await websocket.send_json({
                "status": result["status"],
                "data": {
                    "url": result["url"],
                    "title": result["title"],
                    "timestamp": data["timestamp"]
                }
            })

    except WebSocketDisconnect:
        logger.info("WebSocket connection closed by client")
    except Exception as e:
        logger.error(f"WebSocket error: {str(e)}")
        try:
            await websocket.close()
        except RuntimeError:
            # Connection might already be closed
            pass
    finally:
        logger.info("WebSocket connection closed")

if __name__ == "__main__":
    logger.info("Starting WebSocket server...")
    uvicorn.run(app, host="0.0.0.0", port=8523)
