import asyncio
import aiohttp
from bs4 import BeautifulSoup
from typing import Optional

class PageInfoFetcher:
    async def get_page_title(self, url: str) -> Optional[str]:
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=5) as response:
                    if response.status == 200:
                        html = await response.text()
                        soup = BeautifulSoup(html, 'html.parser')
                        return soup.title.string if soup.title else None
        except:
            return None