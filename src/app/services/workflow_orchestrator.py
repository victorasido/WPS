import os
import tempfile
import asyncio
import logging
import fitz

from src.core.detector import detect_signature_zones
from src.core.converter.converter_service import convert_to_pdf
from src.core.injector import inject_signature
from src.core.docx_injector.docx_injector_service import inject_signature_to_docx, PlaceholderNotFoundError
from src.infra.conversion_queue import conversion_slot, MAX_CONCURRENT_CONVERSIONS, _get_semaphore

logger = logging.getLogger(__name__)


class WorkflowOrchestrator:
    """
    Service layer untuk mengorkestrasikan konversi, deteksi khusus, dan injeksi.
    Memisahkan abstraksi file system (temp files) dari layer bot (Telegram).
    """

    @staticmethod
    async def detect_docx_zones(doc_bytes: bytes, sign_bytes: bytes, doc_name: str, sign_name: str) -> dict:
        """
        Deteksi zona di DOCX.
        Return: {"is_template": bool, "modified_docx": bytes|None, "zones": list, "keyword": str}
        """
        keyword = os.path.splitext(sign_name)[0]
        with tempfile.TemporaryDirectory() as tmpdir:
            docx_path = os.path.join(tmpdir, doc_name)
            sign_path = os.path.join(tmpdir, sign_name)

            with open(docx_path, "wb") as f: f.write(doc_bytes)
            with open(sign_path, "wb") as f: f.write(sign_bytes)

            try:
                # ── Template mode (primary) ──
                modified_docx = inject_signature_to_docx(doc_bytes, sign_path, keyword)
                zones = [{"matched_name": keyword, "confidence": 1.0, "keyword": keyword}]
                return {
                    "is_template": True,
                    "modified_docx": modified_docx,
                    "zones": zones,
                    "keyword": keyword
                }

            except PlaceholderNotFoundError:
                # ── Detector fallback ──
                loop = asyncio.get_event_loop()
                zones = await loop.run_in_executor(
                    None, detect_signature_zones, docx_path, sign_path, 0.4
                )
                return {
                    "is_template": False,
                    "modified_docx": None,
                    "zones": zones,
                    "keyword": keyword
                }


    @staticmethod
    async def process_docx_injection(
        doc_bytes: bytes,
        sign_bytes: bytes,
        sign_name: str,
        selected_zones: list,
        is_template: bool,
        modified_docx: bytes = None,
        on_queued=None,
    ) -> bytes:
        """
        Convert DOCX dan inject TTD, lalu return final PDF bytes.

        Args:
            on_queued: Coroutine opsional yang dipanggil jika konversi harus
                       menunggu slot (semua slot sedang terpakai). Berguna untuk
                       mengirim notifikasi "sedang antri" ke user via Telegram.
        """
        loop = asyncio.get_event_loop()

        # Cek apakah semua slot sedang terpakai sebelum masuk antrian
        sem = _get_semaphore()
        if sem._value == 0 and on_queued is not None:  # type: ignore[attr-defined]
            await on_queued()

        async with conversion_slot():
            with tempfile.TemporaryDirectory() as tmpdir:
                sign_path = os.path.join(tmpdir, sign_name)
                with open(sign_path, "wb") as f: f.write(sign_bytes)

                if is_template:
                    return await loop.run_in_executor(None, convert_to_pdf, modified_docx)
                else:
                    pdf_bytes = await loop.run_in_executor(None, convert_to_pdf, doc_bytes)
                    return await loop.run_in_executor(
                        None, inject_signature, pdf_bytes, sign_path, selected_zones
                    )


    @staticmethod
    async def process_pdf_bypass(doc_bytes: bytes, sign_bytes: bytes, sign_name: str, keyword: str, pages: list[int]) -> bytes:
        """
        Bypass PDF injector.
        Return: Signed PDF bytes. (Raises ValueError jika gagal/keyword tidak ada)
        """
        # Validate existence of keyword early
        doc = fitz.open(stream=doc_bytes, filetype="pdf")
        found = any(page.search_for(keyword) for page in doc)
        doc.close()

        if not found:
            raise ValueError(f"Keyword '{keyword}' tidak ditemukan di PDF.")

        loop = asyncio.get_event_loop()
        with tempfile.TemporaryDirectory() as tmpdir:
            sign_path = os.path.join(tmpdir, sign_name)
            with open(sign_path, "wb") as f: f.write(sign_bytes)

            # Bypass injection trick using paragraph_index 10000 -> pdf_placer forces scan on last 2 pages
            zones_hint = [{
                "matched_name": keyword,
                "keyword": keyword,
                "confidence": 1.0,
                "inject_position": "above_same",
                "source": "pdf_bypass",
                "table_location": None,
                "paragraph_index": 10000, 
            }]

            try:
                return await loop.run_in_executor(
                    None, inject_signature, doc_bytes, sign_path, zones_hint
                )
            except Exception as e:
                logger.error(f"[PDF_BYPASS] inject failed: {e}")
                raise
