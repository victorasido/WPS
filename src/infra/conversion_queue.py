"""
conversion_queue.py
-------------------
Singleton Semaphore untuk membatasi jumlah konversi LibreOffice yang
berjalan bersamaan. Mencegah OOM Killer saat banyak user mengirim DOCX
secara paralel.

Cara pakai:
    from src.infra.conversion_queue import conversion_slot

    async with conversion_slot():
        result = await loop.run_in_executor(None, convert_to_pdf, data)
"""

import asyncio
import logging
import os

logger = logging.getLogger(__name__)

# Batas konversi LibreOffice yang boleh berjalan bersamaan.
# Dapat diubah via env var MAX_CONVERSIONS (default: 3).
MAX_CONCURRENT_CONVERSIONS: int = int(os.getenv("MAX_CONVERSIONS", "3"))

_semaphore: asyncio.Semaphore | None = None


def _get_semaphore() -> asyncio.Semaphore:
    """
    Lazy-init semaphore agar dibuat di dalam event loop yang sama
    dengan coroutine pemanggil (penting untuk asyncio).
    """
    global _semaphore
    if _semaphore is None:
        _semaphore = asyncio.Semaphore(MAX_CONCURRENT_CONVERSIONS)
        logger.info(
            "[ConversionQueue] Semaphore diinisialisasi — "
            "maks %d konversi paralel.",
            MAX_CONCURRENT_CONVERSIONS,
        )
    return _semaphore


class conversion_slot:
    """
    Async context manager untuk mengambil slot konversi.

    Jika semua slot sedang terpakai, coroutine akan suspend (await)
    sampai ada slot kosong — tanpa memblokir event loop utama.

    Usage:
        async with conversion_slot():
            pdf = await loop.run_in_executor(None, convert_to_pdf, docx_bytes)
    """

    async def __aenter__(self):
        sem = _get_semaphore()
        queue_len = MAX_CONCURRENT_CONVERSIONS - sem._value  # type: ignore[attr-defined]
        if queue_len >= MAX_CONCURRENT_CONVERSIONS:
            logger.info(
                "[ConversionQueue] Semua slot penuh (%d/%d). "
                "Menunggu slot kosong...",
                queue_len,
                MAX_CONCURRENT_CONVERSIONS,
            )
        await sem.acquire()
        logger.debug("[ConversionQueue] Slot diperoleh (tersisa: %d).", sem._value)  # type: ignore[attr-defined]
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        _get_semaphore().release()
        logger.debug(
            "[ConversionQueue] Slot dilepas (tersisa: %d).",
            _get_semaphore()._value,  # type: ignore[attr-defined]
        )
        return False  # jangan suppress exception
