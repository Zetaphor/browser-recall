from fastapi import BackgroundTasks
from datetime import datetime, timedelta
import asyncio
from .database import SessionLocal, HistoryEntry, Bookmark
from .browser import BrowserHistoryCollector
from .page_reader import PageReader
from sqlalchemy import func
from sqlalchemy.orm import Session
import pytz

class HistoryScheduler:
    def __init__(self):
        self.browser_collector = BrowserHistoryCollector()
        self.page_reader = PageReader()
        self.last_history_update = None
        self.content_update_interval = timedelta(hours=24)  # Update content daily

    def _normalize_datetime(self, dt: datetime) -> datetime:
        """Convert datetime to UTC if it has timezone, or make it timezone-aware if it doesn't"""
        if dt is None:
            return None

        # If datetime is naive (no timezone), assume it's in UTC
        if dt.tzinfo is None:
            return pytz.UTC.localize(dt)

        # If datetime has timezone, convert to UTC
        return dt.astimezone(pytz.UTC)

    async def update_bookmarks(self):
        bookmarks = self.browser_collector.fetch_bookmarks()

        db = SessionLocal()
        try:
            # First, get all existing URLs to avoid duplicates
            existing_urls = {
                url: (added_time, folder)
                for url, added_time, folder in
                db.query(Bookmark.url, Bookmark.added_time, Bookmark.folder).all()
            }

            new_entries = []
            for added_time, url, title, folder in bookmarks:
                # Normalize the datetime
                added_time = self._normalize_datetime(added_time)

                # Only add if URL doesn't exist or if it's in a different folder
                if (url not in existing_urls or
                    existing_urls[url][1] != folder):
                    domain = self.browser_collector.get_domain(url)
                    entry = Bookmark(
                        url=url,
                        title=title,
                        added_time=added_time,
                        folder=folder,
                        domain=domain
                    )
                    new_entries.append(entry)

            if new_entries:
                db.bulk_save_objects(new_entries)
                db.commit()
        finally:
            db.close()

    async def update_history(self):
        while True:
            db = SessionLocal()
            try:
                # Get the latest timestamp from our database
                latest_entry = db.query(func.max(HistoryEntry.visit_time)).scalar()
                if latest_entry:
                    latest_entry = self._normalize_datetime(latest_entry)

                # Fetch new history
                history = self.browser_collector.fetch_history()

                # Filter to only get entries newer than our latest entry
                new_entries = []
                for visit_time, url, title in history:
                    # Normalize the datetime
                    visit_time = self._normalize_datetime(visit_time)

                    if not latest_entry or visit_time > latest_entry:
                        domain = self.browser_collector.get_domain(url)
                        entry = HistoryEntry(
                            url=url,
                            title=title,
                            visit_time=visit_time,
                            domain=domain
                        )
                        new_entries.append(entry)

                if new_entries:
                    db.bulk_save_objects(new_entries)
                    db.commit()

                # Update bookmarks
                await self.update_bookmarks()

            finally:
                db.close()

            # Wait for 5 minutes before next update
            await asyncio.sleep(300)

    async def close(self):
        """Cleanup resources"""
        await self.page_reader.close()