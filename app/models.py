from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

@dataclass
class NewsItem:
    source: str
    source_id: str
    title: str
    url: str
    published_at: datetime
    body: str = ""
    tickers: list[str] = field(default_factory=list)
    category: str = ""
