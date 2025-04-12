from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import text
from typing import List, Optional

from ..database import get_db, HistoryEntry
from ..utils import serialize_history_entry
from ..logging_config import setup_logger

logger = setup_logger(__name__)
router = APIRouter(prefix="/history", tags=["history"])

@router.get("/search")
async def search_history(
    query: Optional[str] = Query(None),
    domain: Optional[str] = Query(None),
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    include_content: bool = Query(False),
    db: Session = Depends(get_db)
):
    """Search history using FTS5"""
    try:
        if query:
            # Build the FTS query
            # Basic query sanitization/escaping might be needed depending on FTS syntax usage
            # For simple term search, this is okay. For complex FTS syntax, more care is needed.
            fts_conditions = []
            params = {}

            # Handle different query parts (title, content, domain)
            # Example: "term1 title:term2 domain:example.com"
            # This requires more sophisticated parsing. For now, assume simple query applies to title/content.
            # A safer approach for user input:
            sanitized_query = query.replace('"', '""') # Basic FTS escaping for quotes
            fts_match_expr = f'(title : "{sanitized_query}"* OR markdown_content : "{sanitized_query}"*)'
            params['fts_query'] = fts_match_expr

            if domain:
                # Add domain filtering directly in FTS if possible and indexed
                # Assuming 'domain' is an indexed column in FTS table
                # params['fts_query'] += f' AND domain : "{domain}"' # Adjust FTS syntax if needed
                # Or filter after FTS search if domain isn't in FTS index efficiently
                 pass # Domain filtering will be added later if needed

            # Build the SQL query
            sql = """
                SELECT
                    h.*,
                    bm25(history_fts) as rank,
                    highlight(history_fts, 0, '<mark>', '</mark>') as title_highlight,
                    highlight(history_fts, 1, '<mark>', '</mark>') as content_highlight
                FROM history_fts
                JOIN history h ON history_fts.rowid = h.id
                WHERE history_fts MATCH :fts_query
            """

            # Add domain filter as a regular WHERE clause if not in FTS MATCH
            if domain:
                sql += " AND h.domain = :domain"
                params['domain'] = domain

            # Add date filters if provided
            if start_date:
                sql += " AND h.visit_time >= :start_date"
                params['start_date'] = start_date
            if end_date:
                sql += " AND h.visit_time <= :end_date"
                params['end_date'] = end_date

            sql += " ORDER BY rank DESC, h.visit_time DESC LIMIT 100" # Rank usually descends

            results = db.execute(text(sql), params).fetchall()
            # Use the updated serializer that handles potential highlight/rank fields
            return [serialize_history_entry(row, include_content) for row in results]

        else:
            # Handle non-search queries (basic filtering)
            query_builder = db.query(HistoryEntry)

            if domain:
                query_builder = query_builder.filter(HistoryEntry.domain == domain)
            if start_date:
                query_builder = query_builder.filter(HistoryEntry.visit_time >= start_date)
            if end_date:
                query_builder = query_builder.filter(HistoryEntry.visit_time <= end_date)

            entries = query_builder.order_by(HistoryEntry.visit_time.desc()).limit(100).all()
            return [serialize_history_entry(entry, include_content) for entry in entries]

    except Exception as e:
        logger.error(f"Search error: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail={"message": "Search operation failed", "error": str(e)}
        )


@router.get("/search/advanced")
async def advanced_history_search(
    query: str = Query(..., description="Full-text search query with SQLite FTS5 syntax"),
    include_content: bool = Query(False),
    db: Session = Depends(get_db)
):
    """Advanced full-text search using SQLite FTS5 features"""
    try:
        # Use raw SQL for advanced FTS query
        # Add rank and highlights here as well
        fts_query = """
            SELECT
                h.*,
                bm25(history_fts) as rank,
                highlight(history_fts, 0, '<mark>', '</mark>') as title_highlight,
                highlight(history_fts, 1, '<mark>', '</mark>') as content_highlight
            FROM history_fts
            JOIN history h ON history_fts.rowid = h.id
            WHERE history_fts MATCH :query
            ORDER BY rank DESC, h.visit_time DESC
            LIMIT 1000
        """

        results = db.execute(text(fts_query), {'query': query}).fetchall()

        # Use the updated serializer
        return [serialize_history_entry(row, include_content) for row in results]

    except Exception as e:
        logger.error(f"Advanced search error: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail={"message": "Advanced search operation failed", "error": str(e)}
        )