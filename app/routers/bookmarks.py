from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session
from typing import List, Optional

from ..database import get_db, Bookmark
from ..utils import serialize_bookmark
from ..logging_config import setup_logger

logger = setup_logger(__name__)
router = APIRouter(prefix="/bookmarks", tags=["bookmarks"])

@router.get("/search")
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
            # Use LIKE for title search (consider FTS for bookmarks if needed)
            search_pattern = f"%{search_term}%"
            query = query.filter(Bookmark.title.ilike(search_pattern))
            # Removed index hint as SQLAlchemy/SQLite usually handles this well with LIKE

        # Add ordering and limit for better performance
        bookmarks = query.order_by(Bookmark.added_time.desc()).limit(1000).all()

        return [serialize_bookmark(bookmark) for bookmark in bookmarks]

    except Exception as e:
        logger.error(f"Bookmark search error: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail={"message": "Bookmark search operation failed", "error": str(e)}
        )