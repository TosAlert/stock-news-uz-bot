import re

import httpx
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.errors import FloodWaitError, MessageNotModifiedError

from .config import (
    TELEGRAM_API_ID,
    TELEGRAM_API_HASH,
    TELEGRAM_SESSION_STRING,
    TELEGRAM_CHANNEL_ID,
    TELEGRAM_BOT_TOKEN,
)
from .telegram import send_to_chat


_SOURCE_LINE_RE = re.compile(r"^\s*(?:📰\s*)?manba\b", re.IGNORECASE)


def _without_source(raw_text: str, html_text: str):
    raw_lines = raw_text.splitlines()
    html_lines = html_text.splitlines()

    if len(raw_lines) != len(html_lines):
        return None

    removed = False
    new_html_lines = []
    for raw_line, html_line in zip(raw_lines, html_lines):
        if _SOURCE_LINE_RE.match(raw_line):
            removed = True
            continue
        new_html_lines.append(html_line)

    if not removed:
        return None

    while new_html_lines and not new_html_lines[-1].strip():
        new_html_lines.pop()

    return "\n".join(new_html_lines)


async def remove_sources() -> int:
    if not all(
        [
            TELEGRAM_API_ID,
            TELEGRAM_API_HASH,
            TELEGRAM_SESSION_STRING,
            TELEGRAM_CHANNEL_ID,
        ]
    ):
        raise RuntimeError("Telegram MTProto sozlamalari to'liq emas.")

    client = TelegramClient(
        StringSession(TELEGRAM_SESSION_STRING),
        int(TELEGRAM_API_ID),
        TELEGRAM_API_HASH,
    )

    edited = 0
    scanned = 0

    await client.connect()
    try:
        if not await client.is_user_authorized():
            raise RuntimeError("Telegram session avtorizatsiyadan o'tmagan.")

        channel = await client.get_entity(TELEGRAM_CHANNEL_ID)
        me = await client.get_me()
        permissions = await client.get_permissions(channel, me)
        admin_rights = getattr(permissions, "admin_rights", None)
        can_edit = bool(
            getattr(permissions, "is_creator", False)
            or getattr(admin_rights, "edit_messages", False)
        )
        if not can_edit:
            raise RuntimeError(
                "Telegram akkauntida kanaldagi boshqa xabarlarni tahrirlash "
                "huquqi yo'q. Admin huquqlaridan 'Edit Messages'ni yoqing."
            )

        async for message in client.iter_messages(channel, search="Manba"):
            scanned += 1
            if not message.raw_text:
                continue

            new_html = _without_source(
                message.raw_text,
                message.text_html or message.raw_text,
            )
            if new_html is None:
                continue

            try:
                await client.edit_message(
                    channel,
                    message.id,
                    new_html,
                    parse_mode="html",
                    link_preview=False,
                )
                edited += 1
            except MessageNotModifiedError:
                continue
            except FloodWaitError as e:
                raise RuntimeError(
                    f"Telegram flood wait: {e.seconds} soniya kutish kerak."
                ) from e

    finally:
        if client.is_connected():
            await client.disconnect()

    print(f"SOURCE CLEANUP: scanned={scanned} edited={edited}", flush=True)
    return edited


async def _bot_request(method: str, payload=None):
    if not TELEGRAM_BOT_TOKEN:
        raise RuntimeError("Telegram bot token sozlanmagan.")
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/{method}"
    async with httpx.AsyncClient(timeout=20) as client:
        response = await client.post(url, json=payload or {})
        response.raise_for_status()
        data = response.json()
    if not data.get("ok"):
        raise RuntimeError(data.get("description", f"Telegram {method} xatosi"))
    return data.get("result")


async def _can_run_command(user_id: int) -> bool:
    member = await _bot_request(
        "getChatMember",
        {"chat_id": TELEGRAM_CHANNEL_ID, "user_id": user_id},
    )
    status = member.get("status")
    if status == "creator":
        return True
    if status != "administrator":
        return False
    return bool(member.get("can_edit_messages"))


async def process_commands():
    """Process /remove_source commands sent to the bot in private chat."""
    updates = await _bot_request(
        "getUpdates",
        {
            "limit": 100,
            "timeout": 0,
            "allowed_updates": ["message"],
        },
    )
    if not updates:
        return

    highest_update_id = max(int(update["update_id"]) for update in updates)

    for update in updates:
        message = update.get("message") or {}
        chat = message.get("chat") or {}
        if chat.get("type") != "private":
            continue

        text = str(message.get("text") or "").strip()
        command = text.split()[0].split("@", 1)[0].lower() if text else ""
        if command != "/remove_source":
            continue

        sender = message.get("from") or {}
        user_id = sender.get("id")
        chat_id = chat.get("id")
        if not user_id or not chat_id:
            continue

        try:
            allowed = await _can_run_command(int(user_id))
        except Exception as e:
            await send_to_chat(chat_id, "❌ Ruxsatni tekshirishda xato yuz berdi.")
            print(f"COMMAND PERMISSION ERROR: {type(e).__name__}: {e}", flush=True)
            continue

        if not allowed:
            await send_to_chat(
                chat_id,
                "❌ Bu buyruq faqat kanal administratori uchun mavjud.",
            )
            continue

        await send_to_chat(
            chat_id,
            "⏳ Eski xabarlardagi <b>Manba</b> qismi olib tashlanmoqda...",
        )
        try:
            edited = await remove_sources()
            await send_to_chat(
                chat_id,
                f"✅ Tayyor. <b>{edited}</b> ta eski xabar tahrirlandi.",
            )
        except Exception as e:
            print(f"SOURCE CLEANUP ERROR: {type(e).__name__}: {e}", flush=True)
            await send_to_chat(
                chat_id,
                "❌ Tozalashda xato yuz berdi. GitHub Actions logini tekshirish kerak.",
            )

    # Confirm all fetched updates so they are not processed again.
    await _bot_request(
        "getUpdates",
        {
            "offset": highest_update_id + 1,
            "limit": 1,
            "timeout": 0,
            "allowed_updates": ["message"],
        },
    )
