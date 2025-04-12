from typing import Tuple
from urllib.parse import urlparse
from database import Database
from domain_exclusions import DomainExclusions
from logger import Logger
from crawl4ai import AsyncWebCrawler

class BaseCrawler:
    def __init__(self, db: Database, domain_exclusions: DomainExclusions, logger: Logger):
        self.db = db
        self.domain_exclusions = domain_exclusions
        self.logger = logger
        self.crawler = AsyncWebCrawler()

    async def __aenter__(self):
        await self.crawler.__aenter__()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.crawler.__aexit__(exc_type, exc_val, exc_tb)

    def should_skip_url(self, url: str) -> Tuple[bool, str]:
        # Skip about: or chrome: URLs
        if url.startswith("about:") or url.startswith("chrome:"):
            return True, "Browser internal URL"

        # Check domain exclusions using the full URL, not just the domain
        if self.domain_exclusions.is_excluded(url):
            return True, "Excluded domain/path"

        # Check if URL exists
        if self.db.url_exists(url):
            return True, "URL already processed"

        return False, ""

    async def crawl_url(self, url: str, default_title: str = None) -> Tuple[bool, dict]:
        try:
            result = await self.crawler.arun(url=url)
            crawl_result = result[0]
            title = crawl_result.metadata.get('title') or default_title or url.split("/")[-1]
            content = crawl_result.markdown

            self.db.add_history(
                url=url,
                title=title,
                content=content
            )

            return True, {
                "url": url,
                "title": title,
                "status": "received"
            }
        except Exception as e:
            self.logger.error(f"Error processing URL {url}: {str(e)}")
            return False, {
                "url": url,
                "title": default_title or url.split("/")[-1],
                "status": "error",
                "error": str(e)
            }