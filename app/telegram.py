import html
import httpx
from .config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHANNEL_ID, MAX_TELEGRAM_CHARS

def emoji(direction):
    return {"bullish":"🟢", "bearish":"🔴", "mixed":"🟡", "neutral":"⚪"}.get(str(direction).lower(), "🟡")

def _esc(value):
    return html.escape(str(value or ""), quote=True)

def render(item, a):
    tickers = _esc(", ".join(a.get("affected_tickers", [])))
    sectors = _esc(", ".join(a.get("affected_sectors", [])))
    score = a.get("impact_score", 0)
    direction = str(a.get("direction", "neutral")).lower()
    headline = a.get("headline_uz") or item.title
    summary = a.get("summary_uz", "")
    reason = a.get("reason_uz", "")

    parts = [
        f"{emoji(direction)} <b>{_esc(headline)}</b>",
        "",
        _esc(summary),
        "",
        f"<b>Ta'sir:</b> {_esc(direction.upper())} | {score}/10",
        f"<b>Kategoriya:</b> {_esc(a.get('category', 'other'))}",
    ]
    if tickers:
        parts.append(f"<b>Aksiyalar:</b> {tickers}")
    if sectors:
        parts.append(f"<b>Sektor:</b> {sectors}")
    parts += ["", f"<b>Nega muhim:</b> {_esc(reason)}"]
    if item.url:
        parts.append(f'\n📰 <a href="{_esc(item.url)}">Manba</a>')
    return "\n".join(parts)[:MAX_TELEGRAM_CHARS]

async def send(text):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHANNEL_ID:
        raise RuntimeError("Telegram token/channel sozlanmagan.")
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHANNEL_ID,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }
    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.post(url, json=payload)
        r.raise_for_status()
        return r.json()
