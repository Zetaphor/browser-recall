import asyncio
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends, HTTPException
from sqlalchemy.orm import Session
from datetime import datetime, timezone, timedelta
from urllib.parse import urlparse
import iso8601

# Import necessary components from other modules
from .. import main as app_main # To access global crawler instance
from ..database import get_db, HistoryEntry
from ..config import Config
from ..logging_config import setup_logger

logger = setup_logger(__name__)
router = APIRouter(tags=["websocket"])
config = Config() # Assuming config is okay as a separate instance here

@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket, db: Session = Depends(get_db)):
    # Access the global crawler instance from main.py
    crawler = app_main.crawler
    if not crawler:
        logger.error("Crawler not initialized!")
        await websocket.close(code=1011) # Internal Server Error
        return

    logger.info("New WebSocket connection established")
    await websocket.accept()
    try:
        while True:
            data = await websocket.receive_json()

            # Validate incoming data structure (basic check)
            if 'url' not in data or 'timestamp' not in data:
                logger.warning("Received invalid WebSocket message format.")
                await websocket.send_json({
                    "status": "error",
                    "message": "Invalid message format. 'url' and 'timestamp' required."
                })
                continue

            url = data['url']
            try:
                timestamp = iso8601.parse_date(data['timestamp'])
            except iso8601.ParseError:
                logger.warning(f"Received invalid timestamp format: {data['timestamp']}")
                await websocket.send_json({
                    "status": "error",
                    "message": f"Invalid timestamp format: {data['timestamp']}"
                })
                continue

            # Parse the URL and check if domain should be ignored
            try:
                domain = urlparse(url).netloc
                if not domain: # Handle invalid URLs
                     raise ValueError("Could not parse domain from URL")
            except ValueError as e:
                 logger.warning(f"Could not parse URL: {url}. Error: {e}")
                 await websocket.send_json({"status": "error", "message": f"Invalid URL: {url}"})
                 continue

            if config.is_domain_ignored(domain):
                logger.info(f"Ignoring domain: {domain} for URL: {url}")
                await websocket.send_json({
                    "status": "ignored",
                    "message": f"Domain {domain} is in ignore list"
                })
                continue

            logger.info(f"Processing page via WebSocket: {url}")

            # Check if we already have a recent entry for this URL
            # Make timestamp timezone-aware (assuming UTC if naive)
            if timestamp.tzinfo is None:
                timestamp = timestamp.replace(tzinfo=timezone.utc)
            else:
                timestamp = timestamp.astimezone(timezone.utc)

            recent_threshold = timestamp - timedelta(minutes=5)
            existing_entry = db.query(HistoryEntry.id).filter(
                HistoryEntry.url == url,
                HistoryEntry.visit_time >= recent_threshold
            ).first() # Only fetch ID for efficiency

            if existing_entry:
                logger.info(f"Recent entry exists for URL: {url}")
                await websocket.send_json({
                    "status": "skipped",
                    "message": "Recent entry exists"
                })
                continue

            # --- Start crawl4ai processing ---
            logger.info(f"Processing page with crawl4ai: {url}")
            markdown_content = None
            title = ''
            try:
                # Use the global crawler instance
                crawl_result = await crawler.arun(url=url)
                if crawl_result:
                    markdown_content = crawl_result.markdown
                    # Attempt to get title from metadata, fallback to empty string
                    title = getattr(crawl_result.metadata, 'title', '') or '' # Ensure title is string
                    if not title:
                        logger.warning(f"Could not extract title for {url} using crawl4ai.")
                    logger.info(f"crawl4ai processing complete. Markdown length: {len(markdown_content) if markdown_content else 0}, Title: '{title}'")
                else:
                    logger.warning(f"crawl4ai returned None for URL: {url}")
                    markdown_content = "" # Ensure it's not None
                    title = ""

            except Exception as crawl_error:
                logger.error(f"crawl4ai failed for URL {url}: {crawl_error}", exc_info=True)
                await websocket.send_json({
                    "status": "error",
                    "message": f"Failed to crawl page content: {str(crawl_error)}"
                })
                continue # Skip to next message
            # --- End crawl4ai processing ---

            # Only proceed if we got some content or at least a title
            if not title and not markdown_content:
                logger.info(f"No title or content extracted by crawl4ai from: {url}")
                await websocket.send_json({
                    "status": "skipped",
                    "message": "No title or content extracted by crawl4ai"
                })
                continue

            # Create history entry using data from crawl4ai
            history_entry = HistoryEntry(
                url=url,
                title=title, # Use title from crawl4ai
                visit_time=timestamp, # Use the parsed, timezone-aware timestamp
                domain=domain,
                markdown_content=markdown_content, # Use markdown from crawl4ai
                last_content_update=datetime.now(timezone.utc)
            )

            logger.debug(f"Attempting to save entry for {url} with markdown length: {len(markdown_content) if markdown_content else 0}")

            db.add(history_entry)
            try:
                db.commit()
                logger.info(f"Successfully saved entry for: {url}")
                await websocket.send_json({
                    "status": "success",
                    "message": f"Processed page: {url}"
                })
            except Exception as e:
                db.rollback()
                logger.error(f"Error saving entry for {url}: {e}", exc_info=True)
                await websocket.send_json({
                    "status": "error",
                    "message": "Database error occurred while saving."
                })

    except WebSocketDisconnect:
        logger.info("WebSocket client disconnected")
    except Exception as e:
        logger.error(f"Unhandled error in WebSocket handler: {e}", exc_info=True)
        # Attempt to inform client before closing (might fail if connection is already broken)
        try:
            await websocket.send_json({
                "status": "error",
                "message": "An internal server error occurred."
            })
        except Exception:
            pass # Ignore if sending fails
        # Ensure connection is closed on server error
        try:
            await websocket.close(code=1011) # Internal Server Error
        except Exception:
            pass # Ignore if closing fails