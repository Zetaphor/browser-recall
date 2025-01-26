from fastapi import BackgroundTasks
from datetime import datetime, timedelta
import asyncio
from .database import SessionLocal, HistoryEntry, Bookmark, get_last_processed_timestamp, update_last_processed_timestamp
from .browser import BrowserHistoryCollector
from .page_reader import PageReader
from sqlalchemy import func
from sqlalchemy.orm import Session
import pytz
from .config import Config
from .database import get_db
from urllib.parse import urlparse
import logging

logger = logging.getLogger(__name__)

class HistoryScheduler:
    def __init__(self):
        self.browser_collector = BrowserHistoryCollector()
        self.page_reader = PageReader()
        self.last_history_update = None
        self.content_update_interval = timedelta(hours=24)  # Update content daily
        self.config = Config()
        self.db_lock = asyncio.Lock()

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
        """Update bookmarks from browsers"""
        try:
            current_timestamp = int(datetime.now().timestamp())
            source_key = "browser_bookmarks"
            last_timestamp = get_last_processed_timestamp(source_key)

            logger.info(f"Fetching bookmarks. Last processed timestamp: {last_timestamp}")
            bookmarks = self.browser_collector.fetch_bookmarks()
            logger.info(f"Found {len(bookmarks)} total bookmarks")

            # Filter for only new bookmarks
            new_bookmarks = [
                (added_time, url, title, folder) for added_time, url, title, folder in bookmarks
                if self._normalize_datetime(added_time).timestamp() > last_timestamp
            ]

            logger.info(f"Found {len(new_bookmarks)} new bookmarks to process")

            if new_bookmarks:
                async with self.db_lock:
                    with next(get_db()) as db:
                        added_count = 0
                        for added_time, url, title, folder in new_bookmarks:
                            domain = urlparse(url).netloc
                            if self.config.is_domain_ignored(domain):
                                logger.debug(f"Skipping ignored domain: {domain}")
                                continue

                            added_time = self._normalize_datetime(added_time)

                            bookmark = Bookmark(
                                url=url,
                                title=title,
                                added_time=added_time,
                                folder=folder,
                                domain=domain
                            )
                            db.add(bookmark)
                            added_count += 1

                        db.commit()
                        logger.info(f"Successfully added {added_count} new bookmarks")

                update_last_processed_timestamp(source_key, current_timestamp)
                logger.info(f"Updated last processed timestamp to {current_timestamp}")

        except Exception as e:
            logger.error(f"Error updating bookmarks: {str(e)}", exc_info=True)

    async def update_history(self):
        """Background task to update history periodically"""
        while True:
            try:
                current_timestamp = int(datetime.now().timestamp())
                source_key = "browser_history"
                last_timestamp = get_last_processed_timestamp(source_key)

                logger.info(f"Fetching history. Last processed timestamp: {last_timestamp}")
                history_entries = self.browser_collector.fetch_history()
                logger.info(f"Found {len(history_entries)} total history entries")

                # Filter for only new entries
                new_entries = [
                    (visit_time, url, title) for visit_time, url, title in history_entries
                    if self._normalize_datetime(visit_time).timestamp() > last_timestamp
                ]

                logger.info(f"Found {len(new_entries)} new history entries to process")

                if new_entries:
                    async with self.db_lock:
                        with next(get_db()) as db:
                            added_count = 0
                            for visit_time, url, title in new_entries:
                                domain = urlparse(url).netloc
                                if self.config.is_domain_ignored(domain):
                                    logger.debug(f"Skipping ignored domain: {domain}")
                                    continue

                                visit_time = self._normalize_datetime(visit_time)

                                history_entry = HistoryEntry(
                                    url=url,
                                    title=title,
                                    visit_time=visit_time,
                                    domain=domain
                                )
                                db.add(history_entry)
                                added_count += 1

                            db.commit()
                            logger.info(f"Successfully added {added_count} new history entries")

                    update_last_processed_timestamp(source_key, current_timestamp)
                    logger.info(f"Updated last processed timestamp to {current_timestamp}")

            except Exception as e:
                logger.error(f"Error updating history: {str(e)}", exc_info=True)

            await asyncio.sleep(300)  # Wait 5 minutes before next update

    async def close(self):
        """Cleanup resources"""
        await self.page_reader.close()