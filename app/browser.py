from datetime import datetime
from typing import List, Tuple
from browser_history import get_history, get_bookmarks
from urllib.parse import urlparse

class BrowserHistoryCollector:
    @staticmethod
    def get_domain(url: str) -> str:
        return urlparse(url).netloc

    def fetch_history(self) -> List[Tuple[datetime, str, str]]:
        outputs = get_history()
        # Returns list of tuples containing (datetime, url, title)
        return [(entry[0], entry[1], entry[2]) for entry in outputs.histories]

    def fetch_bookmarks(self) -> List[Tuple[datetime, str, str, str]]:
        outputs = get_bookmarks()
        return outputs.bookmarks