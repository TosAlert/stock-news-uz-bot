import feedparser
from datetime import datetime, timezone
from dateutil import parser
from ..models import NewsItem


def _image_from_entry(entry):
    for key in ("media_content", "media_thumbnail"):
        values = entry.get(key, []) or []
        for value in values:
            if isinstance(value, dict) and value.get("url"):
                url = str(value["url"])
                if url.startswith(("https://", "http://")):
                    return url
    for value in entry.get("links", []) or []:
        if not isinstance(value, dict):
            continue
        media_type = str(value.get("type", "")).lower()
        href = str(value.get("href", ""))
        if href.startswith(("https://", "http://")) and media_type.startswith("image/"):
            return href
    return ""


class RSSProvider:
    def __init__(self, urls):
        self.urls = urls
        self.name = "macro_rss"

    async def fetch(self):
        out = []
        for url in self.urls:
            feed = feedparser.parse(url)
            for e in feed.entries:
                title = getattr(e, "title", "")
                link = getattr(e, "link", "")
                sid = getattr(e, "id", None) or link or title
                raw = getattr(e, "published", None) or getattr(e, "updated", None)
                try:
                    dt = parser.parse(raw) if raw else datetime.now(timezone.utc)
                except Exception:
                    dt = datetime.now(timezone.utc)
                summary = getattr(e, "summary", "")
                out.append(NewsItem(
                    source=self.name,
                    source_id=sid,
                    title=title,
                    url=link,
                    published_at=dt,
                    body=summary,
                    image_url=_image_from_entry(e),
                ))
        return out
