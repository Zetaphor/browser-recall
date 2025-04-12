from datetime import datetime
from .database import HistoryEntry, Bookmark

def serialize_history_entry(entry, include_content: bool = False):
    """Serialize a HistoryEntry object or raw SQL result to a dictionary"""
    # Handle both ORM objects and raw SQL results
    if hasattr(entry, '_mapping'):  # Raw SQL result (from execute)
        result = {
            "id": entry.id,
            "url": entry.url,
            "title": entry.title,
            "visit_time": entry.visit_time.isoformat() if isinstance(entry.visit_time, datetime) else entry.visit_time,
            "domain": entry.domain,
            # Add potential highlight fields if they exist
            "title_highlight": getattr(entry, 'title_highlight', None),
            "content_highlight": getattr(entry, 'content_highlight', None),
            "rank": getattr(entry, 'rank', None)
        }
        if include_content:
            # Ensure markdown_content exists before accessing
            result["markdown_content"] = getattr(entry, 'markdown_content', None)

    else:  # ORM object (from query)
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