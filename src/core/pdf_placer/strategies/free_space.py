# services/pdf_placer/strategies/free_space.py
#
# Fallback strategy: no line or grid structure detected.
# Finds whitespace above (or below) each keyword match within its column.

from __future__ import annotations
from typing import List, Optional
import fitz

from ..layout_extractor import PageLayout, TextLine, Column
from ..types import SignaturePlacement
from ..utils.geometry import find_keyword_lines, nearest_above, nearest_below

PAD            = 5.0
MIN_RECT_HEIGHT = 20.0
MAX_SIG_HEIGHT  = 100.0   # cap so signature doesn't take up half the page


def find_placements(
    layout: PageLayout,
    keyword: str,
    page: fitz.Page,
) -> List[SignaturePlacement]:
    """
    For each keyword match, find the best available whitespace in its column.
    Priority: space above → space below → fixed offset above as last resort.
    """
    matches = find_keyword_lines(layout.text_lines, keyword)
    placements = []

    for match in matches:
        col      = _find_column(match, layout.columns)
        col_tl   = _col_lines(layout.text_lines, col)
        rect     = _best_rect(match, col_tl, col)

        if rect is not None and rect.height >= MIN_RECT_HEIGHT:
            placements.append(SignaturePlacement(
                page=page, rect=rect,
                method="free_space", confidence=0.6,
            ))

    return placements


# ── Column helpers ────────────────────────────────────────────

def _find_column(line: TextLine, columns: List[Column]) -> Optional[Column]:
    for col in columns:
        if col.contains_x(line.cx):
            return col
    return min(columns, key=lambda c: abs(c.cx - line.cx)) if columns else None


def _col_lines(text_lines: List[TextLine], col: Optional[Column]) -> List[TextLine]:
    if col is None:
        return text_lines
    return [l for l in text_lines if col.contains_x(l.cx)]


# ── Rect selection ────────────────────────────────────────────

def _best_rect(
    match: TextLine,
    col_lines: List[TextLine],
    col: Optional[Column],
) -> Optional[fitz.Rect]:
    x0 = col.x_min if col else match.x0
    x1 = col.x_max if col else match.x1

    # Option 1: whitespace above match
    above = nearest_above(
        match.y0,
        [l for l in col_lines if l.y1 < match.y0 and l is not match],
        get_y=lambda l: l.y1,
    )
    if above:
        gap = match.y0 - above.y1
        if gap >= MIN_RECT_HEIGHT:
            top = max(above.y1 + PAD, match.y0 - MAX_SIG_HEIGHT)
            return fitz.Rect(x0, top, x1, match.y0 - PAD)

    # Option 2: whitespace below match
    below = nearest_below(
        match.y1,
        [l for l in col_lines if l.y0 > match.y1 and l is not match],
        get_y=lambda l: l.y0,
    )
    if below:
        gap = below.y0 - match.y1
        if gap >= MIN_RECT_HEIGHT:
            bottom = min(below.y0 - PAD, match.y1 + MAX_SIG_HEIGHT)
            return fitz.Rect(x0, match.y1 + PAD, x1, bottom)

    # Option 3: fixed offset above — last resort, never fails
    top = max(0.0, match.y0 - 70.0)
    return fitz.Rect(x0, top, x1, match.y0 - PAD)
