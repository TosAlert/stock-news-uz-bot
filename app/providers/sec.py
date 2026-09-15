import json
import httpx
from datetime import datetime, timezone
from ..config import SEC_USER_AGENT, SEC_COMPANIES_FILE
from ..models import NewsItem

ALLOWED_FORMS = {
    "8-K", "10-Q", "10-K", "6-K", "20-F", "40-F",
    "S-1", "S-3", "13D", "13G"
}

class SECProvider:
    name = "sec"

    def __init__(self):
        self.mapping = json.loads(SEC_COMPANIES_FILE.read_text(encoding="utf-8"))

    async def fetch(self):
        out = []
        today = datetime.now(timezone.utc).date()
        headers = {
            "User-Agent": SEC_USER_AGENT,
            "Accept-Encoding": "gzip, deflate",
        }
        async with httpx.AsyncClient(timeout=20, headers=headers) as client:
            for ticker, cik in self.mapping.items():
                url = f"https://data.sec.gov/submissions/CIK{cik.zfill(10)}.json"
                r = await client.get(url)
                r.raise_for_status()
                data = r.json()
                recent = data.get("filings", {}).get("recent", {})
                forms = recent.get("form", [])
                for i, form in enumerate(forms):
                    if form not in ALLOWED_FORMS:
                        continue
                    acc = recent.get("accessionNumber", [""])[i]
                    filed = recent.get("filingDate", [""])[i]
                    primary = recent.get("primaryDocument", [""])[i]
                    if not acc or not filed or not primary:
                        continue
                    try:
                        dt = datetime.fromisoformat(filed).replace(tzinfo=timezone.utc)
                    except Exception:
                        continue
                    if dt.date() != today:
                        continue

                    filing_url = (
                        f"https://www.sec.gov/Archives/edgar/data/"
                        f"{int(cik)}/{acc.replace('-', '')}/{primary}"
                    )
                    out.append(
                        NewsItem(
                            source=self.name,
                            source_id=acc,
                            title=f"{ticker}: SEC {form} filing",
                            url=filing_url,
                            published_at=dt,
                            body=f"{ticker} filed {form} with the SEC today.",
                            tickers=[ticker],
                            category=form,
                        )
                    )
        return out
