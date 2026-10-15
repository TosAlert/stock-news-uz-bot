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
    return "\n".join(parts)[:MAX_TELEGRAM_CHARS]


async def send_to_chat(chat_id, text, disable_web_page_preview=True):
    if not TELEGRAM_BOT_TOKEN:
        raise RuntimeError("Telegram token sozlanmagan.")
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": disable_web_page_preview,
    }
    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.post(url, json=payload)
        r.raise_for_status()
        data = r.json()
        if not data.get("ok", False):
            raise RuntimeError(f"Telegram sendMessage failed: {data}")
        return data


async def send_photo_to_chat(chat_id, photo_url, caption):
    if not TELEGRAM_BOT_TOKEN:
        raise RuntimeError("Telegram token sozlanmagan.")
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendPhoto"
    payload = {
        "chat_id": chat_id,
        "photo": photo_url,
        "caption": caption,
        "parse_mode": "HTML",
    }
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.post(url, json=payload)
        r.raise_for_status()
        data = r.json()
        if not data.get("ok", False):
            raise RuntimeError(f"Telegram sendPhoto failed: {data}")
        return data


async def send(text):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHANNEL_ID:
        raise RuntimeError("Telegram token/channel sozlanmagan.")
    return await send_to_chat(TELEGRAM_CHANNEL_ID, text)


async def send_news(item, text):
    """Send a source-provided news image with the text when one is available.

    Telegram captions are limited to 1024 characters. For longer analysis, send
    the image first and the complete text as a separate message. If the source
    image URL fails, safely fall back to the existing text-only delivery.
    """
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHANNEL_ID:
        raise RuntimeError("Telegram token/channel sozlanmagan.")

    image_url = str(getattr(item, "image_url", "") or "").strip()
    if not image_url.startswith(("https://", "http://")):
        return await send(text)

    try:
        if len(text) <= 1024:
            return await send_photo_to_chat(TELEGRAM_CHANNEL_ID, image_url, text)

        headline = text.splitlines()[0].strip()[:900]
        await send_photo_to_chat(TELEGRAM_CHANNEL_ID, image_url, headline)
        return await send(text)
    except Exception as e:
        print(f"TELEGRAM IMAGE ERROR: {type(e).__name__}: {e}; falling back to text", flush=True)
        return await send(text)
