"""
services/injector/engine.py
Konduktor pipeline injeksi tanda tangan.

Flow:
    1. Persiapkan signature bytes (prepare_signature)
    2. Coba PRIMARY path: geometry-based placement via pdf_placer
    3. Jika PRIMARY gagal (0 hasil): fallback ke legacy scorer
    4. Insert gambar ke semua placement yang ditemukan
    5. Simpan & return PDF bytes baru

Public API: inject_signature — signature tidak berubah dari versi lama,
semua caller (document_workflow.py) tidak perlu dimodifikasi.
"""

import io
import logging
import fitz
from opentelemetry import trace
from src.infra.telemetry.telemetry_setup import tracer
from src.shared.image_utils import prepare_signature
from .renderer import insert_image
from .legacy_scorer import find_signature_rect

logger = logging.getLogger(__name__)


# ── Main Public API ───────────────────────────────────────────

@tracer.start_as_current_span("inject_signature_pipeline")
def inject_signature(pdf_bytes: bytes, signature_path: str,
                     signature_zones: list) -> bytes:
    """
    Inject signatures into PDF at specified zones.

    Primary path  : geometry-based placement via pdf_placer
                    (layout-aware, handles multi-column, no hardcoded logic)
    Fallback path : legacy keyword-scoring (find_signature_rect)
                    used only if geometry placer returns 0 results

    Public API unchanged — callers (document_workflow.py) need no modification.
    """
    from src.core.pdf_placer import place_all_signatures  # late import (avoid circular)

    span = trace.get_current_span()
    span.set_attribute("pipeline.target_zones_count",
                       len(signature_zones) if signature_zones else 0)
    span.set_attribute("document.pdf_size_bytes", len(pdf_bytes))

    sig_bytes = prepare_signature(signature_path)
    doc       = fitz.open(stream=pdf_bytes, filetype="pdf")

    # Extract keyword: prefer explicit 'keyword' field, fall back to matched_name
    keyword = ""
    if signature_zones:
        keyword = (signature_zones[0].get("keyword")
                   or signature_zones[0].get("matched_name")
                   or "")

    # ── PRIMARY: geometry-based placement ──
    max_count  = len(signature_zones) if signature_zones else None
    placements = place_all_signatures(
        doc, keyword,
        zones_hint=signature_zones,
        max_count=max_count,
    )

    # ── FALLBACK: legacy scorer with dedup guard ──
    if not placements:
        logger.info("[INJ] Geometry placer got 0 results — switching to legacy mode")
        placements = _legacy_place(doc, keyword, signature_zones)

    # ── Insert images ──
    injected_count = 0
    for p in placements:
        logger.info(
            f"[INJ] ✓ [{p.method}] p{p.page.number + 1} "
            f"({p.rect.width:.0f}×{p.rect.height:.0f}pt)"
        )
        insert_image(p.page, p.rect, sig_bytes)
        injected_count += 1

    if injected_count == 0 and signature_zones:
        doc.close()
        raise Exception(f"Gagal inject ke semua zona. Keyword: '{keyword}'")

    buf = io.BytesIO()
    doc.save(buf, deflate=True)
    doc.close()
    return buf.getvalue()


# ── Legacy Fallback ───────────────────────────────────────────

def _legacy_place(doc, keyword: str, zones: list) -> list:
    """
    Legacy per-zone placement menggunakan keyword+scoring approach lama.
    Dilengkapi deduplication guard: zona yang menghasilkan rect yang sama
    (bug lama: 5x Division Head) hanya di-inject sekali.
    """
    from src.core.pdf_placer.types import SignaturePlacement

    placements  = []
    seen_rects: set = set()

    for zone in zones:
        name   = zone.get("matched_name") or keyword
        result = find_signature_rect(doc, name, zone)
        if result is None:
            logger.warning(f"[INJ] ❌ Legacy: gagal detect '{name}'")
            continue

        page, rect, method = result

        # Dedup guard — same rect position = duplicate, skip
        key = (page.number, round(rect.x0), round(rect.y0))
        if key in seen_rects:
            logger.warning(
                f"[INJ] ⚠ Legacy: rect duplikat di p{page.number + 1} "
                f"({rect.x0:.0f},{rect.y0:.0f}), skip"
            )
            continue
        seen_rects.add(key)

        placements.append(SignaturePlacement(
            page=page, rect=rect,
            method=f"legacy_{method}", confidence=0.5,
        ))

    return placements
