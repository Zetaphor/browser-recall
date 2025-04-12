from fastapi import FastAPI, WebSocket
import uvicorn
from logger import Logger
import os
from database import Database
from crawl4ai import AsyncWebCrawler

# Create logs directory if it doesn't exist
os.makedirs('logs', exist_ok=True)

app = FastAPI()
logger = Logger()

db = Database()

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    logger.info("New WebSocket connection established")

    # Create crawler instance outside the loop for reuse
    async with AsyncWebCrawler() as crawler:
        try:
            while True:
                data = await websocket.receive_json()

                # Crawl the URL to get title and content
                try:
                    result = await crawler.arun(url=data["url"])
                    # Get the first result from the container and access metadata
                    crawl_result = result[0]
                    title = crawl_result.metadata.get('title') or data["url"].split("/")[-1]
                    content = crawl_result.markdown
                    logger.info(f"Crawling result: {result}")
                except Exception as crawl_error:
                    logger.error(f"Crawling error for {data['url']}: {str(crawl_error)}")
                    title = data["url"].split("/")[-1]
                    content = str(data)

                # Store received data with crawled information
                db.add_history(
                    url=data["url"],
                    title=title,
                    content=content
                )

                logger.info(f"Processed URL: {data['url']} - {title}")
                await websocket.send_json({
                    "status": "received",
                    "data": {
                        "url": data["url"],
                        "title": title,
                        "timestamp": data["timestamp"]
                    }
                })
        except Exception as e:
            logger.error(f"WebSocket error: {str(e)}")
            await websocket.close()
        finally:
            logger.info("WebSocket connection closed")

if __name__ == "__main__":
    logger.info("Starting WebSocket server...")
    uvicorn.run(app, host="0.0.0.0", port=8523)
