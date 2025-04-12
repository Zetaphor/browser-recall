from fastapi import APIRouter, Depends, Request
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from ..database import get_db, HistoryEntry, Bookmark
from ..logging_config import setup_logger

logger = setup_logger(__name__)
router = APIRouter(tags=["ui"])
templates = Jinja2Templates(directory="app/templates")

@router.get("/")
async def home(request: Request, db: Session = Depends(get_db)):
    try:
        # Get recent history entries
        entries = db.query(HistoryEntry)\
            .order_by(HistoryEntry.visit_time.desc())\
            .limit(50)\
            .all()
        return templates.TemplateResponse(
            "index.html",
            {"request": request, "entries": entries}
        )
    except Exception as e:
        logger.error(f"Error loading home page: {e}", exc_info=True)
        # Optionally return an error template
        return templates.TemplateResponse("error.html", {"request": request, "detail": "Could not load history"})


@router.get("/search")
async def search_page(request: Request):
    return templates.TemplateResponse(
        "search.html",
        {"request": request}
    )


@router.get("/bookmarks")
async def bookmarks_page(request: Request, db: Session = Depends(get_db)):
    try:
        bookmarks = db.query(Bookmark)\
            .order_by(Bookmark.added_time.desc())\
            .limit(50)\
            .all()
        return templates.TemplateResponse(
            "bookmarks.html",
            {"request": request, "bookmarks": bookmarks}
        )
    except Exception as e:
        logger.error(f"Error loading bookmarks page: {e}", exc_info=True)
        # Optionally return an error template
        return templates.TemplateResponse("error.html", {"request": request, "detail": "Could not load bookmarks"})