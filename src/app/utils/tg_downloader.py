from __future__ import annotations

import io

from telegram import Message


async def download_tg_file(message: Message) -> bytes:
    if message.document:
        target = message.document
    elif message.photo:
        target = max(message.photo, key=lambda photo: photo.file_size or 0)
    else:
        raise ValueError("Message does not contain a Telegram document or photo.")

    tg_file = await target.get_file()
    buffer = io.BytesIO()
    await tg_file.download_to_memory(buffer)
    buffer.seek(0)
    return buffer.read()
