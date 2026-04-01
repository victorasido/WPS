# services/pdf_placer/signature_placer.py
# Orchestrator: given an open fitz.Document and a keyword, scan all pages,
# classify each page's layout, pick the right strategy, and collect placements.

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
    Scan every page of `doc`, detect template type, apply matching strategy,
    and return a list of concrete signature placements.

    Args:
        doc         : open fitz.Document (caller owns; do NOT close inside here)
        keyword     : text to search for across all pages
        zones_hint  : optional detector zones (unused for geometry, kept for API compat)
        max_count   : if set, cap the total placements returned (first N in doc order)

    Returns:
        List of SignaturePlacement, each with a valid .page and .rect.
        The caller is responsible for inserting the image and saving the doc.
    """
    if not keyword:
        logger.warning("[PLACER] Empty keyword — returning no placements")
        return []

    all_placements: List[SignaturePlacement] = []

    for page in doc:
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
