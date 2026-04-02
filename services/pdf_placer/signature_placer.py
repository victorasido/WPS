# services/pdf_placer/signature_placer.py
# Orchestrator: given an open fitz.Document and a keyword, scan target pages,
# classify each page's layout, pick the right strategy, and collect placements.
#
# TASK 3 FIX: zones_hint is now used to restrict scanning to hinted pages only,
# preventing over-injection from keyword matches on irrelevant pages.

from __future__ import annotations
import logging
from typing import List, Optional
import fitz

from .layout_extractor import extract_page_layout
from .template_detector import detect_template, TemplateType
from .strategies import line_based, table_based, free_space
from .types import SignaturePlacement
from .utils.geometry import rect_overlaps_text

logger = logging.getLogger(__name__)


def place_all_signatures(
    doc: fitz.Document,
    keyword: str,
    zones_hint: Optional[list] = None,
    max_count:  Optional[int]  = None,
) -> List[SignaturePlacement]:
    """
    Scan halaman PDF, deteksi template, terapkan strategi placement.

    Jika `zones_hint` diberikan (dari DOCX detector), HANYA halaman yang
    direkomendasikan oleh hint tersebut yang akan di-scan. Ini mencegah
    over-injection akibat keyword yang muncul di halaman lain secara tidak sengaja.

    Args:
        doc         : open fitz.Document (caller owns; do NOT close inside here)
        keyword     : text to search for across target pages
        zones_hint  : optional detector zones; digunakan untuk mem-filter halaman
        max_count   : if set, cap the total placements returned (first N in doc order)

    Returns:
        List of SignaturePlacement, each with a valid .page and .rect.
        The caller is responsible for inserting the image and saving the doc.
    """
    if not keyword:
        logger.warning("[PLACER] Empty keyword — returning no placements")
        return []

    # ── Resolusi halaman target dari zones_hint ──────────────────────────────
    target_pages: Optional[set] = None
    if zones_hint:
        target_pages = _resolve_target_pages(doc, zones_hint)
        logger.info(
            f"[PLACER] zones_hint provided — restricting scan to "
            f"page(s): {sorted(p + 1 for p in target_pages)}"
        )

    all_placements: List[SignaturePlacement] = []

    for page in doc:
        # Skip halaman yang tidak direkomendasikan oleh hint
        if target_pages is not None and page.number not in target_pages:
            logger.debug(f"[PLACER] Page {page.number + 1}: skipped (not in hint)")
            continue

        layout   = extract_page_layout(page)
        template = detect_template(layout)

        logger.debug(
            f"[PLACER] Page {page.number + 1}: template={template.value}  "
            f"hlines={len(layout.h_lines)}  cols={len(layout.columns)}  "
            f"grid={layout.has_grid}"
        )

        if template == TemplateType.TABLE_BASED:
            placements = table_based.find_placements(layout, keyword, page)
        elif template == TemplateType.LINE_BASED:
            placements = line_based.find_placements(layout, keyword, page)
        else:
            placements = free_space.find_placements(layout, keyword, page)

        # Filter out placements whose rect contains existing text (overlap guard)
        clean: List[SignaturePlacement] = []
        for p in placements:
            if rect_overlaps_text(p.rect, layout.text_lines):
                logger.debug(
                    f"[PLACER]   ⚠ Skipped (text overlap) {p.method} "
                    f"@ p{page.number + 1} {p.rect}"
                )
            else:
                clean.append(p)

        skipped = len(placements) - len(clean)
        if skipped:
            logger.info(
                f"[PLACER] Page {page.number + 1}: {skipped} placement(s) "
                f"removed (text overlap)"
            )

        logger.info(
            f"[PLACER] Page {page.number + 1}: "
            f"{len(clean)} placement(s) via {template.value}"
        )
        all_placements.extend(clean)

    if max_count is not None and len(all_placements) > max_count:
        logger.info(
            f"[PLACER] Capping {len(all_placements)} placements "
            f"→ {max_count} (zones_hint length)"
        )
        all_placements = all_placements[:max_count]

    return all_placements


def _resolve_target_pages(doc: fitz.Document, zones_hint: list) -> set:
    """
    Ekstrak nomor halaman (0-indexed) yang direkomendasikan dari zones_hint.

    DOCX zones_hint menyimpan `paragraph_index` sebagai proxy urutan dokumen.
    Kita mapping ke halaman PDF dengan heuristik ringan:
      - Table zones (paragraph_index ≥ 10000) → 2 halaman terakhir
      - Paragraph zones → proporsi halaman dari index
      - Jika ada field `page_number` eksplisit → pakai langsung

    Ini jauh lebih presisi daripada scan semua halaman secara buta.
    """
    page_indices: set = set()
    total_pages = doc.page_count

    for zone in zones_hint:
        # Jika ada field page_number eksplisit (0-indexed)
        if "page_number" in zone:
            pg = zone["page_number"]
            if 0 <= pg < total_pages:
                page_indices.add(pg)
            continue

        p_idx = zone.get("paragraph_index", 0)

        if p_idx >= 10000:
            # Table zone — kemungkinan di halaman terakhir dokumen
            for pg in range(max(0, total_pages - 2), total_pages):
                page_indices.add(pg)
        else:
            # Paragraph zone — peta proporsional ke halaman
            estimated = min(int(p_idx / 100), total_pages - 1)
            page_indices.add(estimated)
            # Tambah satu halaman berikutnya sebagai safety margin
            if estimated + 1 < total_pages:
                page_indices.add(estimated + 1)

    # Fallback: jika tidak ada pages terekstrak, scan semua
    if not page_indices:
        logger.warning("[PLACER] _resolve_target_pages: no pages extracted, fallback to all pages")
        return set(range(total_pages))

    return page_indices
