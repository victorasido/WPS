from __future__ import annotations

import io

from telegram import Message

from src.infra.config import (
    TELEGRAM_CONNECT_TIMEOUT,
    TELEGRAM_POOL_TIMEOUT,
    TELEGRAM_READ_TIMEOUT,
    TELEGRAM_WRITE_TIMEOUT,
)


async def download_tg_file(message: Message) -> bytes:
    if message.document:
        target = message.document
    elif message.photo:
        target = max(message.photo, key=lambda photo: photo.file_size or 0)
    else:
        raise ValueError("Message does not contain a Telegram document or photo.")

    tg_file = await target.get_file(
        read_timeout=TELEGRAM_READ_TIMEOUT,
        write_timeout=TELEGRAM_WRITE_TIMEOUT,
        connect_timeout=TELEGRAM_CONNECT_TIMEOUT,
        pool_timeout=TELEGRAM_POOL_TIMEOUT,
    )
    buffer = io.BytesIO()
    await tg_file.download_to_memory(
        buffer,
        read_timeout=TELEGRAM_READ_TIMEOUT,
        write_timeout=TELEGRAM_WRITE_TIMEOUT,
        connect_timeout=TELEGRAM_CONNECT_TIMEOUT,
        pool_timeout=TELEGRAM_POOL_TIMEOUT,
    )
    buffer.seek(0)
    return buffer.read()
