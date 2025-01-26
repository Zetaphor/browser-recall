from fastapi import FastAPI, Depends, Query
from sqlalchemy.orm import Session
from datetime import datetime
from typing import List
import asyncio

from .database import get_db, HistoryEntry, Bookmark
from .scheduler import HistoryScheduler

app = FastAPI()
scheduler = HistoryScheduler()

@app.on_event("startup")
async def startup_event():
    # Initial bookmark fetch
    await scheduler.update_bookmarks()
    # Start the background task
    asyncio.create_task(scheduler.update_history())

@app.get("/history/search")
async def search_history(
    domain: str = Query(None),
    start_date: datetime = Query(None),
    end_date: datetime = Query(None),
    search_term: str = Query(None),
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
        query = query.filter(HistoryEntry.title.ilike(f"%{search_term}%"))

    return query.all()

@app.get("/bookmarks/search")
async def search_bookmarks(
    domain: str = Query(None),
    folder: str = Query(None),
    search_term: str = Query(None),
    db: Session = Depends(get_db)
):
    query = db.query(Bookmark)

    if domain:
        query = query.filter(Bookmark.domain == domain)

    if folder:
        query = query.filter(Bookmark.folder == folder)

    if search_term:
        query = query.filter(Bookmark.title.ilike(f"%{search_term}%"))

    return query.all()