from fastapi import BackgroundTasks
from datetime import datetime, timedelta
import asyncio
from .database import SessionLocal, HistoryEntry, Bookmark
from .browser import BrowserHistoryCollector
from .page_reader import PageReader
from sqlalchemy import func
from sqlalchemy.orm import Session
import pytz
from .config import Config
from .database import get_db
from urllib.parse import urlparse

class HistoryScheduler:
    def __init__(self):
        self.browser_collector = BrowserHistoryCollector()
        self.page_reader = PageReader()
        self.last_history_update = None
        self.content_update_interval = timedelta(hours=24)  # Update content daily
        self.config = Config()

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
        """Update bookmarks from browser"""
        try:
            db = next(get_db())
            bookmarks = self.browser_collector.fetch_bookmarks()

            for added_time, url, title, folder in bookmarks:  # Unpack the tuple
                # Extract domain and check if it should be ignored
                domain = urlparse(url).netloc
                if self.config.is_domain_ignored(domain):
                    continue

                # Normalize the datetime
                added_time = self._normalize_datetime(added_time)

                # Process the bookmark only if domain is not ignored
                bookmark_entry = Bookmark(
                    url=url,
                    title=title,
                    added_time=added_time,
                    folder=folder,
                    domain=domain
                )
                db.add(bookmark_entry)

            db.commit()

        except Exception as e:
            print(f"Error updating bookmarks: {e}")
        finally:
            db.close()

    async def update_history(self):
        """Background task to update history periodically"""
        while True:
            try:
                db = next(get_db())
                history_entries = self.browser_collector.fetch_history()

                for visit_time, url, title in history_entries:  # Unpack the tuple
                    # Extract domain and check if it should be ignored
                    domain = urlparse(url).netloc
                    if self.config.is_domain_ignored(domain):
                        continue

                    # Normalize the datetime
                    visit_time = self._normalize_datetime(visit_time)

                    # Process the entry only if domain is not ignored
                    history_entry = HistoryEntry(
                        url=url,
                        title=title,
                        visit_time=visit_time,
                        domain=domain
                    )
                    db.add(history_entry)

                db.commit()

            except Exception as e:
                print(f"Error updating history: {e}")
            finally:
                db.close()

            await asyncio.sleep(300)  # Wait 5 minutes before next update

    async def close(self):
        """Cleanup resources"""
        await self.page_reader.close()