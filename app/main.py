from fastapi import FastAPI, Depends, Query, WebSocket, WebSocketDisconnect, HTTPException
from sqlalchemy.orm import Session
from datetime import datetime, timezone, timedelta
from typing import List, Optional
import asyncio
from fastapi import WebSocketDisconnect
from urllib.parse import urlparse
import pytz
from fastapi.middleware.cors import CORSMiddleware
import iso8601
from bs4 import BeautifulSoup
from sqlalchemy import text
from sqlalchemy.sql import text
from .logging_config import setup_logger
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi import Request
import browser_history
from .database import (
    get_db,
    HistoryEntry,
    Bookmark,
    get_last_processed_timestamp,
    update_last_processed_timestamp,
    create_tables,
    engine
)
from .scheduler import HistoryScheduler
from .page_info import PageInfo
from .page_reader import PageReader
from .config import Config

logger = setup_logger(__name__)

app = FastAPI()
scheduler = HistoryScheduler()
config = Config()

# Add CORS middleware to allow WebSocket connections
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, specify your domains
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

templates = Jinja2Templates(directory="app/templates")
app.mount("/static", StaticFiles(directory="app/static"), name="static")

@app.on_event("startup")
async def startup_event():
    logger.info("Starting application")

    # Create necessary tables
    create_tables()

    # Initial history and bookmark fetch
    try:
        # Process history
        process_browser_history()

        # Process bookmarks
        await scheduler.update_bookmarks()

        # Start the background tasks
        asyncio.create_task(scheduler.update_history())
    except Exception as e:
        logger.error(f"Error during startup: {str(e)}")

def serialize_history_entry(entry, include_content: bool = False):
    """Serialize a HistoryEntry object to a dictionary"""
    # Handle both ORM objects and raw SQL results
    if hasattr(entry, '_mapping'):  # Raw SQL result
        result = {
            "id": entry.id,
            "url": entry.url,
            "title": entry.title,
            "visit_time": entry.visit_time.isoformat() if isinstance(entry.visit_time, datetime) else entry.visit_time,
            "domain": entry.domain,
        }
    else:  # ORM object
        result = {
            "id": entry.id,
            "url": entry.url,
            "title": entry.title,
            "visit_time": entry.visit_time.isoformat() if entry.visit_time else None,
            "domain": entry.domain,
        }

    if include_content:
        result["markdown_content"] = entry.markdown_content
    return result

def serialize_bookmark(bookmark):
    """Serialize a Bookmark object to a dictionary"""
    return {
        "id": bookmark.id,
        "url": bookmark.url,
        "title": bookmark.title,
        "added_time": bookmark.added_time.isoformat() if bookmark.added_time else None,
        "folder": bookmark.folder,
        "domain": bookmark.domain,
    }

@app.get("/history/search")
async def search_history(
    domain: Optional[str] = Query(None),
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    search_term: Optional[str] = Query(None),
    include_content: bool = Query(False),
    db: Session = Depends(get_db)
):
    """Search history with optimized full-text search"""
    try:
        if search_term:
            # Modified query to handle title-only searches better
            fts_query = """
                WITH RECURSIVE
                ranked_results AS (
                    SELECT DISTINCT h.*,
                        CASE
                            -- Boost exact title matches highest
                            WHEN h.title LIKE :exact_pattern THEN 4.0
                            -- Boost title prefix matches
                            WHEN h.title LIKE :prefix_pattern THEN 3.0
                            -- Boost title contains matches
                            WHEN h.title LIKE :like_pattern THEN 2.0
                            -- Lower boost for content matches
                            WHEN h.markdown_content IS NOT NULL AND (
                                h.markdown_content LIKE :exact_pattern OR
                                h.markdown_content LIKE :prefix_pattern OR
                                h.markdown_content LIKE :like_pattern
                            ) THEN 1.0
                            ELSE 0.5
                        END * (
                            CAST(strftime('%s', h.visit_time) AS INTEGER) /
                            CAST(strftime('%s', 'now') AS INTEGER) * 0.5 + 1
                        ) as final_rank
                    FROM history h
                    LEFT JOIN history_fts f ON h.id = f.rowid
                    WHERE
                        h.title LIKE :like_pattern
                        OR (h.markdown_content IS NOT NULL AND history_fts MATCH :search)
                        AND (:domain IS NULL OR h.domain = :domain)
                        AND (:start_date IS NULL OR h.visit_time >= :start_date)
                        AND (:end_date IS NULL OR h.visit_time <= :end_date)
                )
                SELECT * FROM ranked_results
                WHERE final_rank > 0
                ORDER BY final_rank DESC
                LIMIT 100
            """

            # Prepare search patterns for different matching strategies
            params = {
                'search': f'{search_term}*',  # Wildcard suffix matching
                'like_pattern': f'%{search_term}%',  # Contains matching
                'exact_pattern': search_term,  # Exact matching
                'prefix_pattern': f'{search_term}%',  # Prefix matching
                'domain': domain,
                'start_date': start_date,
                'end_date': end_date
            }

            # Execute with connection context manager
            with engine.connect() as connection:
                results = connection.execute(text(fts_query), params).all()
                return [serialize_history_entry(row, include_content) for row in results]
        else:
            # Optimize non-FTS query
            query = db.query(HistoryEntry)

            if domain:
                query = query.filter(HistoryEntry.domain == domain)
            if start_date:
                query = query.filter(HistoryEntry.visit_time >= start_date)
            if end_date:
                query = query.filter(HistoryEntry.visit_time <= end_date)

            # Add index hints and limit
            query = query.with_hint(HistoryEntry, 'INDEXED BY ix_history_visit_time', 'sqlite')
            entries = query.order_by(HistoryEntry.visit_time.desc()).limit(100).all()
            return [serialize_history_entry(entry, include_content) for entry in entries]

    except Exception as e:
        logger.error(f"Search error: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail={"message": "Search operation failed", "error": str(e)}
        )

@app.get("/bookmarks/search")
async def search_bookmarks(
    domain: Optional[str] = Query(None),
    folder: Optional[str] = Query(None),
    search_term: Optional[str] = Query(None),
    db: Session = Depends(get_db)
):
    """Search bookmarks with optimized queries"""
    try:
        # Build query efficiently
        query = db.query(Bookmark)

        # Apply filters using index-optimized queries
        if domain:
            query = query.filter(Bookmark.domain == domain)

        if folder:
            query = query.filter(Bookmark.folder == folder)

        if search_term:
            # Use LIKE with index hint for title search
            search_pattern = f"%{search_term}%"
            query = query.filter(
                Bookmark.title.ilike(search_pattern)
            ).with_hint(
                Bookmark,
                'INDEXED BY ix_bookmarks_title',
                'sqlite'
            )

        # Add ordering and limit for better performance
        bookmarks = query.order_by(Bookmark.added_time.desc()).limit(1000).all()

        return [serialize_bookmark(bookmark) for bookmark in bookmarks]

    except Exception as e:
        print(f"Bookmark search error: {e}")
        raise HTTPException(status_code=500, detail="Search operation failed")

# Add new endpoint for advanced full-text search
@app.get("/history/search/advanced")
async def advanced_history_search(
    query: str = Query(..., description="Full-text search query with SQLite FTS5 syntax"),
    include_content: bool = Query(False),
    db: Session = Depends(get_db)
):
    """Advanced full-text search using SQLite FTS5 features"""
    try:
        # Use raw SQL for advanced FTS query
        fts_query = """
            SELECT h.*, rank
            FROM history h
            INNER JOIN history_fts f ON h.id = f.rowid
            WHERE history_fts MATCH :query
            ORDER BY rank
            LIMIT 1000
        """

        results = db.execute(text(fts_query), {'query': query}).all()

        # Convert results to HistoryEntry objects
        entries = [
            serialize_history_entry(
                HistoryEntry(
                    id=row.id,
                    url=row.url,
                    title=row.title,
                    visit_time=row.visit_time,
                    domain=row.domain,
                    markdown_content=row.markdown_content if include_content else None
                ),
                include_content
            )
            for row in results
        ]

        return entries

    except Exception as e:
        print(f"Advanced search error: {e}")
        raise HTTPException(status_code=500, detail="Advanced search operation failed")

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket, db: Session = Depends(get_db)):
    logger.info("New WebSocket connection established")
    page_reader = PageReader()
    await websocket.accept()
    try:
        while True:
            data = await websocket.receive_json()

            # Parse the URL and check if domain should be ignored
            domain = urlparse(data['url']).netloc
            if config.is_domain_ignored(domain):
                logger.info(f"Ignoring domain: {domain}")
                await websocket.send_json({
                    "status": "ignored",
                    "message": f"Domain {domain} is in ignore list"
                })
                continue

            logger.info(f"Processing page: {data['url']}")
            timestamp = iso8601.parse_date(data['timestamp'])

            # Check if we already have a recent entry for this URL
            existing_entry = db.query(HistoryEntry).filter(
                HistoryEntry.url == data['url'],
                HistoryEntry.visit_time >= timestamp - timedelta(minutes=5)
            ).first()

            if existing_entry:
                print(f"Recent entry exists for URL: {data['url']}")
                await websocket.send_json({
                    "status": "skipped",
                    "message": "Recent entry exists"
                })
                continue

            page_info = PageInfo(
                url=data['url'],
                html=data['html'],
                timestamp=timestamp
            )

            # Debug HTML content
            print(f"HTML content length before processing: {len(page_info.html)}")

            # Extract title
            soup = BeautifulSoup(page_info.html, 'html.parser')
            title = soup.title.string if soup.title else ''
            print(f"Extracted title: {title}")

            # Debug markdown conversion
            print("Starting markdown conversion...")
            cleaned_html = page_reader.clean_html(page_info.html)
            print(f"Cleaned HTML length: {len(cleaned_html)}")

            markdown_content = page_reader.html_to_markdown(page_info.html)
            print(f"Markdown conversion complete. Content length: {len(markdown_content) if markdown_content else 0}")

            if markdown_content:
                print("First 100 chars of markdown:", markdown_content[:100])
            else:
                print("No markdown content generated")

            if not title and not markdown_content:
                print(f"No content extracted from: {page_info.url}")
                await websocket.send_json({
                    "status": "skipped",
                    "message": "No content extracted"
                })
                continue

            # Create history entry
            history_entry = HistoryEntry(
                url=page_info.url,
                title=title,
                visit_time=page_info.timestamp,
                domain=domain,
                markdown_content=markdown_content,
                last_content_update=datetime.now(timezone.utc)
            )

            # Debug database operation
            print(f"Saving entry with markdown length: {len(markdown_content) if markdown_content else 0}")

            # Use bulk operations for better performance
            db.add(history_entry)

            try:
                db.commit()
                print(f"Successfully saved entry for: {page_info.url}")
                print(f"Verify markdown content length in database: {len(history_entry.markdown_content) if history_entry.markdown_content else 0}")
                await websocket.send_json({
                    "status": "success",
                    "message": f"Processed page: {page_info.url}"
                })
            except Exception as e:
                db.rollback()
                print(f"Error saving entry: {e}")
                await websocket.send_json({
                    "status": "error",
                    "message": "Database error"
                })

    except WebSocketDisconnect:
        logger.info("Client disconnected")
    except Exception as e:
        logger.error("Error in WebSocket handler", exc_info=True)
    finally:
        await page_reader.close()

@app.get("/config/ignored-domains")
async def get_ignored_domains():
    """Get list of ignored domain patterns"""
    return {"ignored_domains": config.config.get('ignored_domains', [])}

@app.post("/config/ignored-domains")
async def add_ignored_domain(pattern: str):
    """Add a new domain pattern to ignored list"""
    config.add_ignored_domain(pattern)
    return {"status": "success", "message": f"Added pattern: {pattern}"}

@app.delete("/config/ignored-domains/{pattern}")
async def remove_ignored_domain(pattern: str):
    """Remove a domain pattern from ignored list"""
    config.remove_ignored_domain(pattern)
    return {"status": "success", "message": f"Removed pattern: {pattern}"}

@app.get("/")
async def home(request: Request, db: Session = Depends(get_db)):
    # Get recent history entries
    entries = db.query(HistoryEntry)\
        .order_by(HistoryEntry.visit_time.desc())\
        .limit(50)\
        .all()
    return templates.TemplateResponse(
        "index.html",
        {"request": request, "entries": entries}
    )

@app.get("/search")
async def search_page(request: Request):
    return templates.TemplateResponse(
        "search.html",
        {"request": request}
    )

@app.get("/bookmarks")
async def bookmarks_page(request: Request, db: Session = Depends(get_db)):
    bookmarks = db.query(Bookmark)\
        .order_by(Bookmark.added_time.desc())\
        .limit(50)\
        .all()
    return templates.TemplateResponse(
        "bookmarks.html",
        {"request": request, "bookmarks": bookmarks}
    )

def process_browser_history():
    try:
        logger.info("Starting browser history processing")
        outputs = browser_history.get_history()
        history_list = outputs.histories  # This is a list of tuples (timestamp, url, title)
        logger.info(f"Found {len(history_list)} total history items")

        current_timestamp = int(datetime.now().timestamp())
        source_key = "browser_history"  # Single source since we get combined history
        last_timestamp = get_last_processed_timestamp(source_key)

        logger.info(f"Last processed timestamp: {last_timestamp}")

        # Filter for only new entries
        new_entries = [
            entry for entry in history_list
            if entry[0].timestamp() > last_timestamp
        ]

        logger.info(f"Found {len(new_entries)} new entries")

        if new_entries:
            for timestamp, url, title in new_entries:
                logger.info(f"Processing entry: {timestamp} - {url}")
                domain = urlparse(url).netloc
                if config.is_domain_ignored(domain):
                    logger.debug(f"Skipping ignored domain: {domain}")
                    continue

                # Create history entry
                db = next(get_db())
                try:
                    history_entry = HistoryEntry(
                        url=url,
                        title=title,
                        visit_time=timestamp,
                        domain=domain
                    )
                    db.add(history_entry)
                    db.commit()
                except Exception as e:
                    logger.error(f"Error storing history item: {str(e)}")
                    db.rollback()
                finally:
                    db.close()

            # Update the last processed timestamp
            update_last_processed_timestamp(source_key, current_timestamp)
            logger.info(f"Updated timestamp to {current_timestamp}")

        logger.info(f"Processed {len(new_entries)} new items")

    except Exception as e:
        logger.error(f"Error processing browser history: {str(e)}", exc_info=True)