import httpx
from datetime import datetime, timezone, timedelta
from dateutil import parser
from ..config import ALPACA_API_KEY, ALPACA_API_SECRET, ALPACA_PAGE_LIMIT
from ..models import NewsItem

class AlpacaNewsProvider:
    name = "alpaca"

    async def fetch(self, tickers=None, since_minutes: int | None = None):
        if not ALPACA_API_KEY or not ALPACA_API_SECRET:
            return []

        headers = {
            "APCA-API-KEY-ID": ALPACA_API_KEY,
            "APCA-API-SECRET-KEY": ALPACA_API_SECRET,
        }
        params = {
            "limit": ALPACA_PAGE_LIMIT,
            "sort": "desc",
        }
        if tickers:
            params["symbols"] = ",".join(tickers)
        if since_minutes:
            start = datetime.now(timezone.utc) - timedelta(minutes=since_minutes)
            params["start"] = start.isoformat().replace("+00:00", "Z")

        async with httpx.AsyncClient(timeout=20, headers=headers) as client:
            r = await client.get(
                "https://data.alpaca.markets/v1beta1/news",
                params=params
            )
            r.raise_for_status()
            data = r.json()

        out = []
        for x in data.get("news", []):
            title = x.get("headline") or ""
            if not title:
                continue
            sid = str(x.get("id") or x.get("url") or title)
            raw = x.get("created_at") or x.get("updated_at")
            try:
                dt = parser.parse(raw) if raw else datetime.now(timezone.utc)
            except Exception:
                dt = datetime.now(timezone.utc)

            symbols = [str(s).upper() for s in (x.get("symbols") or [])]
            images = x.get("images") or []
            image_url = ""
            if isinstance(images, list):
                # Alpaca news images commonly provide small, medium, and large variants.
                ordered = sorted(
                    (img for img in images if isinstance(img, dict) and img.get("url")),
                    key=lambda img: {"large": 0, "medium": 1, "small": 2}.get(
                        str(img.get("size", "")).lower(), 3
                    ),
                )
                if ordered:
                    image_url = str(ordered[0].get("url") or "")

            out.append(
                NewsItem(
                    source=self.name,
                    source_id=sid,
                    title=title,
                    url=x.get("url") or "",
                    published_at=dt,
                    body=x.get("summary") or "",
                    image_url=image_url,
                    tickers=symbols,
                    category="",
                )
            )
        return out
