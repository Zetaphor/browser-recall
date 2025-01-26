import re
from markdownify import markdownify as md
from bs4 import BeautifulSoup
from typing import Optional
from urllib.parse import urlparse
from .config import ReaderConfig
import logging
from .database import SessionLocal, BlacklistedDomain

# Setup logging with less verbose output
logging.basicConfig(
    level=logging.WARNING,
    format='%(levelname)s: %(message)s'
)
logger = logging.getLogger(__name__)

# Patterns for cleaning
SCRIPT_PATTERN = r"<[ ]*script.*?\/[ ]*script[ ]*>"
STYLE_PATTERN = r"<[ ]*style.*?\/[ ]*style[ ]*>"
META_PATTERN = r"<[ ]*meta.*?>"
COMMENT_PATTERN = r"<[ ]*!--.*?--[ ]*>"
LINK_PATTERN = r"<[ ]*link.*?>"
BASE64_IMG_PATTERN = r'<img[^>]+src="data:image/[^;]+;base64,[^"]+"[^>]*>'
SVG_PATTERN = r"(<svg[^>]*>)(.*?)(<\/svg>)"

class PageReader:
    def __init__(self):
        self.config = ReaderConfig()
        self.db = SessionLocal()

    def clean_html(self, html: str) -> str:
        """Clean HTML by removing unwanted elements and patterns."""
        if not html:
            return ""

        # First use regex to remove problematic patterns
        html = re.sub(SCRIPT_PATTERN, "", html, flags=re.IGNORECASE | re.MULTILINE | re.DOTALL)
        html = re.sub(STYLE_PATTERN, "", html, flags=re.IGNORECASE | re.MULTILINE | re.DOTALL)
        html = re.sub(META_PATTERN, "", html, flags=re.IGNORECASE | re.MULTILINE | re.DOTALL)
        html = re.sub(COMMENT_PATTERN, "", html, flags=re.IGNORECASE | re.MULTILINE | re.DOTALL)
        html = re.sub(LINK_PATTERN, "", html, flags=re.IGNORECASE | re.MULTILINE | re.DOTALL)
        html = re.sub(SVG_PATTERN, "", html, flags=re.IGNORECASE | re.MULTILINE | re.DOTALL)
        html = re.sub(BASE64_IMG_PATTERN, "", html)

        try:
            # Use BeautifulSoup to remove additional elements we want to strip
            soup = BeautifulSoup(html, 'html.parser')

            # Remove unwanted elements
            elements_to_remove = [
                'canvas', 'img', 'picture', 'audio', 'video',
                'iframe', 'embed', 'object', 'param', 'track',
                'map', 'area', 'source'
            ]

            for element in elements_to_remove:
                for tag in soup.find_all(element):
                    tag.decompose()

            return str(soup)
        except Exception as e:
            logger.error(f"Error cleaning HTML: {e}")
            return ""

    def clean_whitespace(self, text: str) -> str:
        """Clean excessive whitespace from text."""
        if not text:
            return ""

        try:
            # Replace 3 or more newlines with 2 newlines
            cleaned = re.sub(r'\n{3,}', '\n\n', text)
            # Remove trailing whitespace from each line
            cleaned = '\n'.join(line.rstrip() for line in cleaned.splitlines())
            return cleaned.strip()
        except Exception as e:
            logger.error(f"Error cleaning whitespace: {e}")
            return ""

    def html_to_markdown(self, html: str) -> Optional[str]:
        """Convert HTML to markdown."""
        try:
            cleaned_html = self.clean_html(html)
            if not cleaned_html:
                return None

            return self.clean_whitespace(md(cleaned_html,
                                          heading_style="ATX",
                                          bullets="-",
                                          autolinks=True,
                                          strip=['form'],
                                          escape_asterisks=True,
                                          escape_underscores=True))

        except Exception as e:
            logger.error(f"Error converting to markdown: {e}")
            return None

    def close(self):
        """Cleanup resources"""
        self.db.close()