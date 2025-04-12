from datetime import datetime, timedelta, timezone
import asyncio
from sqlalchemy import or_, update
from .database import HistoryEntry, Bookmark, get_last_processed_timestamp, update_last_processed_timestamp
from .browser import BrowserHistoryCollector
from .config import Config
from .database import get_db
import urllib.parse
import logging
from crawl4ai import AsyncWebCrawler
from typing import Optional

logger = logging.getLogger(__name__)

class HistoryScheduler:
    def __init__(self, crawler: AsyncWebCrawler):
        self.browser_collector = BrowserHistoryCollector()
        self.last_history_update = None
        self.content_update_interval = timedelta(hours=24)  # Update content daily
        self.config = Config()
        self.db_lock = asyncio.Lock()
        self.crawler = crawler

    def _normalize_datetime(self, dt: datetime) -> Optional[datetime]:
        """Convert datetime to UTC if it has timezone, or make it timezone-aware (UTC) if it doesn't"""
        if dt is None:
            return None

        # If datetime is naive (no timezone), assume it's local and convert to UTC
        if dt.tzinfo is None or dt.tzinfo.utcoffset(dt) is None:
            # Assume local timezone if naive, then convert to UTC
            # This might need adjustment based on where the naive datetime originates
            # If browser_history always returns naive UTC, use: dt.replace(tzinfo=timezone.utc)
            # If browser_history returns naive local time:
            dt = dt.astimezone() # Make timezone-aware using system's local timezone
            return dt.astimezone(timezone.utc) # Convert to UTC

        # If datetime already has timezone, convert to UTC
        return dt.astimezone(timezone.utc)

    async def update_bookmarks(self):
        """Update bookmarks from browsers"""
        try:
            # Use timezone-aware current time
            current_timestamp_dt = datetime.now(timezone.utc)
            current_timestamp = int(current_timestamp_dt.timestamp())
            source_key = "browser_bookmarks"
            # Ensure last_timestamp is 0 if None
            last_timestamp = get_last_processed_timestamp(source_key) or 0

            logger.info(f"Fetching bookmarks. Last processed timestamp (UTC epoch): {last_timestamp}")
            bookmarks = self.browser_collector.fetch_bookmarks()
            logger.info(f"Found {len(bookmarks)} total bookmarks")

            new_bookmarks = []
            skipped_ignored = 0
            processed_urls = set() # Avoid processing duplicate bookmark URLs within the same batch

            for added_time, url, title, folder in bookmarks:
                if not url or url in processed_urls: # Skip empty or duplicate URLs in this batch
                    continue

                # Normalize timestamp *before* comparison
                normalized_added_time = self._normalize_datetime(added_time)
                if normalized_added_time is None:
                    logger.warning(f"Skipping bookmark with invalid timestamp: {url} - {title}")
                    continue

                # Compare timestamps after normalization
                if normalized_added_time.timestamp() > last_timestamp:
                    domain = urllib.parse.urlparse(url).netloc
                    if self.config.is_domain_ignored(domain):
                        # logger.debug(f"Skipping ignored domain for bookmark: {domain}")
                        skipped_ignored += 1
                        continue

                    new_bookmarks.append((normalized_added_time, url, title, folder, domain))
                    processed_urls.add(url) # Mark URL as processed for this batch

            logger.info(f"Found {len(new_bookmarks)} new bookmarks to process after filtering.")
            if skipped_ignored > 0:
                logger.info(f"Skipped {skipped_ignored} bookmarks due to ignored domains.")


            if new_bookmarks:
                async with self.db_lock:
                    # Use context manager for session
                    with next(get_db()) as db:
                        added_count = 0
                        try:
                            for norm_added_time, url, title, folder, domain in new_bookmarks:
                                # Optional: Check if bookmark already exists (by URL)
                                # existing = db.query(Bookmark.id).filter(Bookmark.url == url).first()
                                # if existing:
                                #     logger.debug(f"Bookmark already exists: {url}")
                                #     continue

                                bookmark = Bookmark(
                                    url=url,
                                    title=title or "", # Ensure title is not None
                                    added_time=norm_added_time,
                                    folder=folder or "", # Ensure folder is not None
                                    domain=domain
                                )
                                db.add(bookmark)
                                added_count += 1

                            if added_count > 0:
                                db.commit()
                                logger.info(f"Successfully committed {added_count} new bookmarks.")
                                # Update timestamp only if new bookmarks were added
                                update_last_processed_timestamp(source_key, current_timestamp)
                                logger.info(f"Updated last processed bookmark timestamp for '{source_key}' to {current_timestamp}")
                            else:
                                logger.info("No new unique bookmarks to add in this batch.")
                                # Optionally update timestamp even if no *new* bookmarks were added,
                                # to signify the check was performed up to 'current_timestamp'.
                                # update_last_processed_timestamp(source_key, current_timestamp)
                                # logger.info(f"Updated last processed bookmark timestamp check for '{source_key}' to {current_timestamp}")


                        except Exception as e:
                            logger.error(f"Error committing bookmarks: {str(e)}", exc_info=True)
                            db.rollback()
            else:
                logger.info("No new bookmarks found since last check.")
                # Update timestamp to indicate the check was performed
                update_last_processed_timestamp(source_key, current_timestamp)
                logger.info(f"Updated last processed bookmark timestamp check for '{source_key}' to {current_timestamp}")


        except Exception as e:
            logger.error(f"Error updating bookmarks: {str(e)}", exc_info=True)


    async def update_history(self):
        """Background task to update history periodically"""
        # Initial sleep to allow startup tasks (like initial sync) to potentially finish first
        await asyncio.sleep(10)
        while True:
            try:
                # Use timezone-aware current time
                current_timestamp_dt = datetime.now(timezone.utc)
                current_timestamp = int(current_timestamp_dt.timestamp())
                source_key = "browser_history_scheduler" # Use a different key than initial sync
                # Ensure last_timestamp is 0 if None
                last_timestamp = get_last_processed_timestamp(source_key) or 0

                logger.info(f"Scheduler: Fetching history. Last processed timestamp (UTC epoch): {last_timestamp}")
                history_entries = self.browser_collector.fetch_history()
                logger.info(f"Scheduler: Found {len(history_entries)} total history entries from browser.")

                new_entries = []
                skipped_ignored = 0
                processed_urls_times = set() # Avoid duplicates within the batch (url, timestamp)

                for visit_time, url, title in history_entries:
                     # Basic validation
                    if not url or not visit_time:
                        logger.warning(f"Scheduler: Skipping entry with missing URL or timestamp: {title}")
                        continue

                    # Normalize timestamp *before* comparison
                    normalized_visit_time = self._normalize_datetime(visit_time)
                    if normalized_visit_time is None:
                        logger.warning(f"Scheduler: Skipping history with invalid timestamp: {url} - {title}")
                        continue

                    # Compare timestamps after normalization
                    if normalized_visit_time.timestamp() > last_timestamp:
                        entry_key = (url, normalized_visit_time.timestamp())
                        if entry_key in processed_urls_times:
                            continue # Skip duplicate within this batch

                        domain = urllib.parse.urlparse(url).netloc
                        if self.config.is_domain_ignored(domain):
                            # logger.debug(f"Scheduler: Skipping ignored domain: {domain}")
                            skipped_ignored += 1
                            continue

                        new_entries.append((normalized_visit_time, url, title, domain))
                        processed_urls_times.add(entry_key)

                logger.info(f"Scheduler: Found {len(new_entries)} new history entries to process after filtering.")
                if skipped_ignored > 0:
                    logger.info(f"Scheduler: Skipped {skipped_ignored} history entries due to ignored domains.")

                if new_entries:
                    async with self.db_lock:
                        # Use context manager for session
                        with next(get_db()) as db:
                            added_count = 0
                            try:
                                for norm_visit_time, url, title, domain in new_entries:
                                    # Optional: More robust check if entry already exists
                                    # existing = db.query(HistoryEntry.id).filter(
                                    #     HistoryEntry.url == url,
                                    #     HistoryEntry.visit_time == norm_visit_time
                                    # ).first()
                                    # if existing:
                                    #     logger.debug(f"Scheduler: History entry already exists: {url} at {norm_visit_time}")
                                    #     continue

                                    history_entry = HistoryEntry(
                                        url=url,
                                        title=title or "", # Ensure title is not None
                                        visit_time=norm_visit_time,
                                        domain=domain
                                        # markdown_content is initially NULL
                                    )
                                    db.add(history_entry)
                                    added_count += 1

                                if added_count > 0:
                                    db.commit()
                                    logger.info(f"Scheduler: Successfully committed {added_count} new history entries.")
                                    # Update timestamp only if new entries were added
                                    update_last_processed_timestamp(source_key, current_timestamp)
                                    logger.info(f"Scheduler: Updated last processed history timestamp for '{source_key}' to {current_timestamp}")
                                else:
                                    logger.info("Scheduler: No new unique history entries to add in this batch.")
                                    # Optionally update timestamp even if no *new* entries were added
                                    # update_last_processed_timestamp(source_key, current_timestamp)
                                    # logger.info(f"Scheduler: Updated last processed history timestamp check for '{source_key}' to {current_timestamp}")

                            except Exception as e:
                                logger.error(f"Scheduler: Error committing history: {str(e)}", exc_info=True)
                                db.rollback()
                else:
                    logger.info("Scheduler: No new history entries found since last check.")
                    # Update timestamp to indicate the check was performed
                    update_last_processed_timestamp(source_key, current_timestamp)
                    logger.info(f"Scheduler: Updated last processed history timestamp check for '{source_key}' to {current_timestamp}")


            except Exception as e:
                logger.error(f"Scheduler: Error in update_history loop: {str(e)}", exc_info=True)

            # --- Access config value using property ---
            try:
                # Use direct attribute access via the @property
                wait_time = self.config.history_update_interval_seconds
            except Exception as config_err:
                logger.error(f"Scheduler (History): Error accessing config for wait time, using default 300s. Error: {config_err}")
                wait_time = 300
            # --- End Access ---

            logger.debug(f"Scheduler (History): Sleeping for {wait_time} seconds.")
            await asyncio.sleep(wait_time) # Use the obtained wait_time

    async def _process_markdown_batch(self):
        """Fetches and processes one batch (up to 10) of history entries needing markdown."""
        entries_to_process = []
        try:
            # --- Query for entries (inside DB lock/session) ---
            async with self.db_lock:
                with next(get_db()) as db:
                    # Find up to 10 entries where markdown_content is NULL or empty string
                    entries_to_process = db.query(HistoryEntry).filter(
                        or_(HistoryEntry.markdown_content == None, HistoryEntry.markdown_content == '')
                    ).order_by(HistoryEntry.visit_time.asc()).limit(10).all()

                    if entries_to_process:
                        logger.info(f"Markdown Processor: Found {len(entries_to_process)} entries to process in this batch.")
                        for entry in entries_to_process:
                            db.expunge(entry) # Detach before async operations
                    else:
                        logger.info("Markdown Processor: No history entries found needing markdown update in this batch.")
                        return # Nothing to do in this batch


            # --- Crawling and Updating (outside the DB lock/session) ---
            processed_count = 0
            skipped_ignored = 0
            for entry in entries_to_process:
                markdown_content = None
                crawl_success = False
                should_update_db = False

                # --- ADD DOMAIN CHECK ---
                try:
                    # +++ Add Debugging Lines +++
                    logger.debug(f"Debugging urllib.parse type: {type(urllib.parse)}")
                    logger.debug(f"Is 'urlparse' in urllib.parse? {'urlparse' in dir(urllib.parse)}")
                    # +++ End Debugging Lines +++

                    domain = urllib.parse.urlparse(entry.url).netloc
                    if self.config.is_domain_ignored(domain):
                        logger.debug(f"Markdown Processor: Skipping ignored domain: {domain} for URL: {entry.url} (ID={entry.id})")
                        skipped_ignored += 1
                        continue
                except Exception as parse_err:
                     logger.warning(f"Markdown Processor: Error parsing URL to get domain: {entry.url} (ID={entry.id}). Type={type(parse_err).__name__} Error: {parse_err}. Skipping entry.")
                     continue
                # --- END DOMAIN CHECK ---


                try:
                    logger.info(f"Markdown Processor: Crawling URL: {entry.url} (ID={entry.id})")
                    if not self.crawler:
                        logger.error("Markdown Processor: Crawler not initialized!")
                        break # Stop processing this batch if crawler is missing

                    result = await self.crawler.arun(url=entry.url)

                    if result and result.markdown:
                        markdown_content = result.markdown
                        crawl_success = True
                        logger.info(f"Markdown Processor: Successfully crawled and got markdown for ID={entry.id}.")
                    else:
                        logger.warning(f"Markdown Processor: Crawling completed but no markdown content found for ID={entry.id}, URL={entry.url}")
                        markdown_content = "" # Mark as processed without content
                        crawl_success = True

                    should_update_db = True

                except Exception as crawl_error:
                    logger.error(f"Markdown Processor: Error crawling URL {entry.url} (ID={entry.id}) Type={type(crawl_error).__name__}: {crawl_error}", exc_info=False)
                    should_update_db = False # Don't update DB on crawl error

                # --- Update DB for this specific entry ---
                if should_update_db:
                    try:
                        async with self.db_lock:
                            with next(get_db()) as db_update:
                                stmt = (
                                    update(HistoryEntry)
                                    .where(HistoryEntry.id == entry.id)
                                    .values(markdown_content=markdown_content)
                                )
                                result_proxy = db_update.execute(stmt)
                                if result_proxy.rowcount > 0:
                                    db_update.commit()
                                    # Adjust log message based on whether it was skipped or processed
                                    if markdown_content == "" and crawl_success and not result.markdown: # Check if marked empty due to no content
                                         logger.info(f"Markdown Processor: Marked entry as processed (no content found) for ID={entry.id}.")
                                    elif crawl_success:
                                         logger.info(f"Markdown Processor: Successfully updated markdown status for ID={entry.id}.")

                                    # Only increment processed_count if actual content was added or marked empty after crawl
                                    if markdown_content is not None: # Includes actual markdown or empty string marker
                                        processed_count += 1
                                else:
                                    logger.warning(f"Markdown Processor: Could not find entry ID={entry.id} to update markdown status (rowcount 0).")
                                    db_update.rollback()
                    except Exception as db_update_error:
                        logger.error(f"Markdown Processor: Error updating database for ID={entry.id}: {db_update_error}", exc_info=True)

            log_suffix = f"Updated {processed_count}"
            if skipped_ignored > 0:
                log_suffix += f", Skipped {skipped_ignored} (ignored domain)"
            log_suffix += f" out of {len(entries_to_process)} entries in this batch."
            logger.info(f"Markdown Processor: Finished processing batch. {log_suffix}")


        except Exception as e:
            logger.error(f"Markdown Processor: Error processing markdown batch: {str(e)}", exc_info=True)


    async def update_missing_markdown_periodically(self):
        """Periodically triggers the processing of batches of history entries needing markdown."""
        # Initial slight delay to ensure startup tasks settle
        await asyncio.sleep(15)
        logger.info("Starting periodic markdown update task...")
        while True:
            await self._process_markdown_batch() # Process one batch

            # Wait before checking for the next batch
            # --- Access config value using property ---
            try:
                # Use direct attribute access via the @property
                wait_time = self.config.markdown_update_interval_seconds
            except Exception as config_err:
                logger.error(f"Periodic Markdown Updater: Error accessing config for wait time, using default 300s. Error: {config_err}")
                wait_time = 300
            # --- End Access ---

            logger.debug(f"Periodic Markdown Updater: Sleeping for {wait_time} seconds before next batch.")
            await asyncio.sleep(wait_time)

    async def close(self):
        """Cleanup resources"""
        logger.info("Closing scheduler resources...")
        # Add any specific cleanup needed for BrowserHistoryCollector if necessary
        # The crawler is managed and closed (if needed) in main.py's shutdown
        pass