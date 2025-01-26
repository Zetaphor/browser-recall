from dataclasses import dataclass
from datetime import datetime

@dataclass
class PageInfo:
    url: str
    html: str
    timestamp: datetime