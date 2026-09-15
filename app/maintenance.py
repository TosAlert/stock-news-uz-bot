import re
from typing import Optional

from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.errors import FloodWaitError, MessageNotModifiedError

from .config import (
    TELEGRAM_API_ID,
    TELEGRAM_API_HASH,
    TELEGRAM_SESSION_STRING,
    TELEGRAM_CHANNEL_ID,
)


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

        async for message in client.iter_messages(
            channel,
            search="Manba",
        ):
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
                await client.disconnect()
                raise RuntimeError(
                    f"Telegram flood wait: {e.seconds} soniya kutish kerak."
                ) from e

    finally:
        if client.is_connected():
            await client.disconnect()

    print(f"SOURCE CLEANUP: scanned={scanned} edited={edited}", flush=True)
    return edited
