from fastapi import FastAPI, Depends
from sqlalchemy.orm import Session
from datetime import datetime, timezone
from typing import Optional
import asyncio
from urllib.parse import urlparse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
import browser_history
from crawl4ai import AsyncWebCrawler

# Local imports
from .logging_config import setup_logger
from .database import (
    get_db,
    HistoryEntry,
    get_last_processed_timestamp,
    update_last_processed_timestamp,
    create_tables,
    engine,
    # recreate_fts_tables # Keep if needed, but often done manually or via migration tool
)
from .config import Config

# Import Routers
from .routers import history, bookmarks, config as api_config, websocket, ui

logger = setup_logger(__name__)

# --- Global Variables ---
# These are accessed by other modules (like websocket router)
# Consider using app state or dependency injection for cleaner management if complexity grows
config_manager = Config() # Renamed to avoid conflict with router import
crawler: Optional[AsyncWebCrawler] = None

# Import scheduler *after* crawler is defined
from .scheduler import HistoryScheduler
scheduler: Optional[HistoryScheduler] = None # Now initialize scheduler variable

# --- FastAPI App Initialization ---
app = FastAPI(title="Browser History Search API")

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Adjust in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static files and templates
app.mount("/static", StaticFiles(directory="app/static"), name="static")
# Note: Templates are used within the ui router now, no need for global instance here unless used elsewhere

# --- Helper Function (Initial Sync) ---
def process_browser_history():
    """Fetches and stores new history entries from browser_history library (Initial Sync)."""
    try:
        logger.info("Starting browser history processing (initial sync)")
        outputs = browser_history.get_history()
        # browser_history returns platform specific History object, get histories list
        history_list = []
        if hasattr(outputs, 'histories') and outputs.histories:
             history_list = outputs.histories # List of (datetime, url, title)
        else:
             logger.warning("Could not retrieve histories list from browser_history output.")
             return # Exit if no history list found

        logger.info(f"Found {len(history_list)} total history items from browser_history library")

        current_timestamp_dt = datetime.now(timezone.utc)
        current_timestamp = int(current_timestamp_dt.timestamp()) # Use timezone-aware timestamp
        source_key = "browser_history_sync" # Differentiate from scheduler source
        last_timestamp = get_last_processed_timestamp(source_key) or 0 # Ensure it's 0 if None

        logger.info(f"Last processed timestamp for initial sync '{source_key}': {last_timestamp}")

        new_entries = []
        processed_urls_times = set() # Avoid duplicates within the batch

        for entry in history_list:
            # Basic validation of entry structure
            if not isinstance(entry, (tuple, list)) or len(entry) < 2:
                logger.warning(f"Skipping malformed history entry: {entry}")
                continue
            timestamp, url = entry[0], entry[1]
            title = entry[2] if len(entry) > 2 else "" # Handle optional title

            if not url or not timestamp:
                logger.warning(f"Skipping entry with missing URL or timestamp: Title='{title}'")
                continue

            # Ensure timestamp is datetime object
            if not isinstance(timestamp, datetime):
                 logger.warning(f"Skipping entry with non-datetime timestamp ({type(timestamp)}): {url}")
                 continue

            # Normalize timestamp (Assume local if naive, convert to UTC)
            if timestamp.tzinfo is None or timestamp.tzinfo.utcoffset(timestamp) is None:
                try:
                    timestamp_aware = timestamp.astimezone() # Make aware using system local
                except Exception as tz_err:
                     logger.warning(f"Could not determine local timezone for naive timestamp {timestamp}. Assuming UTC. Error: {tz_err}")
                     timestamp_aware = timestamp.replace(tzinfo=timezone.utc) # Fallback to UTC
            else:
                timestamp_aware = timestamp
            timestamp_utc = timestamp_aware.astimezone(timezone.utc)


            # Filter for only new entries based on normalized UTC timestamp
            if timestamp_utc.timestamp() > last_timestamp:
                entry_key = (url, timestamp_utc.timestamp())
                if entry_key in processed_urls_times:
                    continue # Skip duplicate within this batch

                new_entries.append((timestamp_utc, url, title))
                processed_urls_times.add(entry_key)

        logger.info(f"Found {len(new_entries)} new entries for initial sync after filtering")

        if new_entries:
            added_count = 0
            skipped_ignored = 0
            # Use context manager for session
            with next(get_db()) as db:
                try:
                    for timestamp_utc, url, title in new_entries:
                        domain = urlparse(url).netloc
                        if config_manager.is_domain_ignored(domain):
                            # logger.debug(f"Skipping ignored domain during initial sync: {domain}")
                            skipped_ignored += 1
                            continue

                        # Optional: Check if entry already exists more robustly
                        # existing = db.query(HistoryEntry.id).filter(HistoryEntry.url == url, HistoryEntry.visit_time == timestamp_utc).first()
                        # if existing:
                        #     continue

                        history_entry = HistoryEntry(
                            url=url,
                            title=title or "", # Ensure title is not None
                            visit_time=timestamp_utc,
                            domain=domain
                            # Note: No markdown content here, only basic history
                        )
                        db.add(history_entry)
                        added_count += 1

                    if added_count > 0:
                        db.commit()
                        logger.info(f"Committed {added_count} new history entries from initial sync.")
                        # Update the last processed timestamp only if successful commit
                        update_last_processed_timestamp(source_key, current_timestamp)
                        logger.info(f"Updated initial sync timestamp for '{source_key}' to {current_timestamp}")
                    else:
                         logger.info("No new unique entries to commit during initial sync.")
                         # Update timestamp even if nothing new added, to mark sync time
                         update_last_processed_timestamp(source_key, current_timestamp)
                         logger.info(f"Updated initial sync timestamp check for '{source_key}' to {current_timestamp}")


                    if skipped_ignored > 0:
                        logger.info(f"Skipped {skipped_ignored} entries due to ignored domains during initial sync.")

                except Exception as e:
                    logger.error(f"Error storing history item during initial sync: {str(e)}", exc_info=True)
                    db.rollback()
        else:
             logger.info("No new history entries found during initial sync.")
             # Update timestamp even if nothing new found, to mark sync time
             update_last_processed_timestamp(source_key, current_timestamp)
             logger.info(f"Updated initial sync timestamp check for '{source_key}' to {current_timestamp}")


    except ImportError:
         logger.warning("`browser_history` library not found or import failed. Skipping initial sync.")
    except Exception as e:
        logger.error(f"Error processing browser history during initial sync: {str(e)}", exc_info=True)


# --- Startup and Shutdown Events ---
@app.on_event("startup")
async def startup_event():
    global crawler, scheduler # Allow modification of globals
    logger.info("Starting application initialization...")

    try:
        # 1. Ensure base tables exist
        logger.info("Ensuring base tables exist...")
        create_tables()

        # 2. Initialize the crawler
        logger.info("Initializing AsyncWebCrawler...")
        if crawler is None:
             crawler = AsyncWebCrawler()
        logger.info("AsyncWebCrawler initialized.")

        # 3. Initialize the Scheduler *after* the crawler
        logger.info("Initializing HistoryScheduler...")
        if scheduler is None:
            scheduler = HistoryScheduler(crawler=crawler) # Pass crawler instance
        logger.info("HistoryScheduler initialized.")

        # 4. Perform initial history sync from browser_history library
        logger.info("Performing initial browser history sync...")
        process_browser_history() # Sync history not processed before

        # 5. Perform initial bookmark sync (using scheduler's method)
        # Run in background to avoid blocking startup if it takes long
        logger.info("Starting initial bookmark sync task...")
        asyncio.create_task(scheduler.update_bookmarks())

        # 6. Start background tasks (scheduler for ongoing updates)
        logger.info("Starting background history update task...")
        asyncio.create_task(scheduler.update_history())

        # --- Markdown Update Tasks ---
        # 7a. Trigger ONE initial batch processing run in the background
        logger.info("Starting initial markdown processing batch task...")
        asyncio.create_task(scheduler._process_markdown_batch()) # Run one batch now

        # 7b. Start the PERIODIC background markdown update task
        logger.info("Starting periodic background markdown update task...")
        # Use the renamed method for the loop
        asyncio.create_task(scheduler.update_missing_markdown_periodically())
        # --- End Markdown Update Tasks ---


        logger.info("Application startup sequence initiated. Background tasks running.")

    except Exception as e:
        logger.error(f"FATAL ERROR during application startup: {str(e)}", exc_info=True)
        raise RuntimeError(f"Application startup failed: {e}") from e


@app.on_event("shutdown")
async def shutdown_event():
    global crawler, scheduler
    logger.info("Starting application shutdown...")

    # Stop scheduler tasks gracefully if possible (implement cancellation in tasks if needed)
    # For now, we just close resources

    # Close scheduler resources
    if scheduler and hasattr(scheduler, 'close'):
         try:
             logger.info("Closing scheduler resources...")
             await scheduler.close() # Call the scheduler's close method
         except Exception as e:
             logger.error(f"Error closing scheduler: {e}", exc_info=True)

    # Close crawler if needed (check crawl4ai docs for explicit close method)
    # Based on previous code, seems no explicit close needed, but keep check just in case
    if crawler and hasattr(crawler, 'aclose'):
        try:
            logger.info("Closing AsyncWebCrawler...")
            # await crawler.aclose() # Example if an async close exists
        except Exception as e:
            logger.error(f"Error closing crawler: {e}", exc_info=True)


    # Close database engine connections if necessary (usually handled automatically by SQLAlchemy)
    # if engine and hasattr(engine, 'dispose'): # Check if using async engine that needs dispose
    #    await engine.dispose()

    logger.info("Application shutdown complete.")


# --- Include Routers ---
app.include_router(history.router)
app.include_router(bookmarks.router)
app.include_router(api_config.router)
app.include_router(websocket.router)
app.include_router(ui.router)

# Optional: Add a root endpoint for health check or basic info
@app.get("/health", tags=["service"])
async def health_check():
    # Extended health check could verify DB connection or task status
    db_ok = False
    try:
        with next(get_db()) as db:
            db.execute("SELECT 1")
            db_ok = True
    except Exception:
        db_ok = False

    return {
        "status": "ok",
        "database_connection": "ok" if db_ok else "error",
        # Add other checks as needed
    }