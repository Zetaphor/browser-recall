from fastapi import FastAPI, Depends, Query, WebSocket, WebSocketDisconnect
from sqlalchemy.orm import Session
from datetime import datetime, timezone
from typing import List, Optional
import asyncio
from fastapi import WebSocketDisconnect
from urllib.parse import urlparse
import pytz
from fastapi.middleware.cors import CORSMiddleware
import iso8601

from .database import get_db, HistoryEntry, Bookmark
from .scheduler import HistoryScheduler
from .page_info import PageInfo
from .page_reader import PageReader

app = FastAPI()
scheduler = HistoryScheduler()

# Add CORS middleware to allow WebSocket connections
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, specify your domains
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
async def startup_event():
    # Initial bookmark fetch
    await scheduler.update_bookmarks()
    # Start the background task
    asyncio.create_task(scheduler.update_history())

def serialize_history_entry(entry, include_content: bool = False):
    """Serialize a HistoryEntry object to a dictionary"""
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
    start_date: Optional[datetime] = Query(None),
    end_date: Optional[datetime] = Query(None),
    search_term: Optional[str] = Query(None),
    include_content: bool = Query(False),
    db: Session = Depends(get_db)
):
    query = db.query(HistoryEntry)

    if domain:
        query = query.filter(HistoryEntry.domain == domain)

    if start_date:
        query = query.filter(HistoryEntry.visit_time >= start_date)

    if end_date:
        query = query.filter(HistoryEntry.visit_time <= end_date)

    if search_term:
        query = query.filter(
            (HistoryEntry.title.ilike(f"%{search_term}%")) |
            (HistoryEntry.markdown_content.ilike(f"%{search_term}%"))
        )

    entries = query.all()
    return [serialize_history_entry(entry, include_content) for entry in entries]

@app.get("/bookmarks/search")
async def search_bookmarks(
    domain: Optional[str] = Query(None),
    folder: Optional[str] = Query(None),
    search_term: Optional[str] = Query(None),
    db: Session = Depends(get_db)
):
    query = db.query(Bookmark)

    if domain:
        query = query.filter(Bookmark.domain == domain)

    if folder:
        query = query.filter(Bookmark.folder == folder)

    if search_term:
        query = query.filter(Bookmark.title.ilike(f"%{search_term}%"))

    bookmarks = query.all()
    return [serialize_bookmark(bookmark) for bookmark in bookmarks]

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket, db: Session = Depends(get_db)):
    print("WebSocket endpoint called")
    page_reader = PageReader()
    print("New WebSocket connection established")
    await websocket.accept()
    print("WebSocket connection accepted")
    try:
        while True:
            print("Waiting for message...")
            data = await websocket.receive_json()
            print(f"Received message for URL: {data['url']}")
            print(f"HTML content length: {len(data['html'])}")
            print(f"Timestamp: {data['timestamp']}")

            # Parse the ISO timestamp correctly
            timestamp = iso8601.parse_date(data['timestamp'])

            page_info = PageInfo(
                url=data['url'],
                html=data['html'],
                timestamp=timestamp
            )
            print(f"Created PageInfo object for: {page_info.url}")

            # Convert HTML to markdown
            print("Converting HTML to markdown...")
            markdown_content = page_reader.html_to_markdown(page_info.html)
            print(f"Markdown conversion complete, length: {len(markdown_content) if markdown_content else 0}")

            # Update or create history entry
            domain = urlparse(page_info.url).netloc
            print(f"Creating history entry for domain: {domain}")
            history_entry = HistoryEntry(
                url=page_info.url,
                visit_time=page_info.timestamp,
                domain=domain,
                markdown_content=markdown_content,
                last_content_update=datetime.now(timezone.utc)
            )

            print("Saving to database...")
            db.add(history_entry)
            db.commit()
            print("Database save complete")

            # Send confirmation back to client
            await websocket.send_json({
                "status": "success",
                "message": f"Processed page: {page_info.url}"
            })

    except WebSocketDisconnect:
        print("Client disconnected")
    except Exception as e:
        print(f"Error handling message: {e}")
        # Send error back to client if possible
        try:
            await websocket.send_json({
                "status": "error",
                "message": str(e)
            })
        except:
            pass
    finally:
        print("Cleaning up resources")
        page_reader.close()