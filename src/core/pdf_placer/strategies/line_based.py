# services/pdf_placer/strategies/line_based.py
#
# Handles documents where signature slots are defined by horizontal separator
# lines (drawn lines or text dashes like "--------").
#
# Pattern (Document 1 — Deliverable Acceptance Certificate):
#   [blank space]          ← signature goes here
#   - - - - - - - - -     ← separator line
#   Division Head          ← keyword match
#   Divisi CISO
#   PT. Bank Negara Indonesia

from __future__ import annotations
from typing import List, Optional
import fitz

from ..layout_extractor import PageLayout, TextLine, HLine, Column
from ..types import SignaturePlacement
from ..utils.geometry import find_keyword_lines, nearest_above, nearest_below

# Max height for a generated signature rect — avoids huge zones
MAX_SIG_HEIGHT = 110.0
# Padding inside the rect so signature doesn't glue to a line
PAD = 5.0
# How far above/below the keyword to look for a separator line
SEPARATOR_SEARCH_RADIUS = 250.0
# Minimum usable height for a placement to be returned
MIN_RECT_HEIGHT = 20.0


def find_placements(
    layout: PageLayout,
    keyword: str,
    page: fitz.Page,
) -> List[SignaturePlacement]:
    """
    For each keyword match on this page, find the nearest separator line
    and compute the signature rect in the empty space created by that line.
    Each match produces at most one placement.
    """
    matches = find_keyword_lines(layout.text_lines, keyword)
    placements = []

    for match in matches:
        col   = _find_column(match, layout.columns)
        rect  = _rect_for_match(match, col, layout)
        if rect is not None and rect.height >= MIN_RECT_HEIGHT:
            placements.append(SignaturePlacement(
                page=page, rect=rect,
                method="line_based", confidence=0.9,
            ))

    return placements


# ── Column helpers ────────────────────────────────────────────

def _find_column(line: TextLine, columns: List[Column]) -> Optional[Column]:
    for col in columns:
        if col.contains_x(line.cx):
            return col
    # Nearest column as fallback
    return min(columns, key=lambda c: abs(c.cx - line.cx)) if columns else None


def _col_lines(text_lines: List[TextLine], col: Optional[Column]) -> List[TextLine]:
    if col is None:
        return text_lines
    return [l for l in text_lines if col.contains_x(l.cx)]


def _col_hlines(h_lines: List[HLine], col: Optional[Column]) -> List[HLine]:
    if col is None:
        return h_lines
    # An HLine belongs to a column if it horizontally intersects the column bounds
    return [h for h in h_lines if h.x0 <= col.x_max + 25 and h.x1 >= col.x_min - 25]


# ── Core placement logic ──────────────────────────────────────

def _rect_for_match(
    match: TextLine,
    col: Optional[Column],
    layout: PageLayout,
) -> Optional[fitz.Rect]:
    """
    Try three placement options in priority order:
      1. Empty space ABOVE a separator line that sits above the keyword
         (most common: blank space → dash line → keyword text)
      2. Plain whitespace above the keyword (no separator line present)
      3. Empty space BELOW a separator line that sits below the keyword
         (label→space→name pattern: keyword → dash line → next content)
    """
    x0 = col.x_min if col else match.x0
    x1 = col.x_max if col else match.x1

    col_tl = _col_lines(layout.text_lines, col)
    col_hl = _col_hlines(layout.h_lines, col)

    # ── Option 1: separator above keyword ──
    hline_above = nearest_above(
        match.y0,
        [h for h in col_hl if (match.y0 - h.y) <= SEPARATOR_SEARCH_RADIUS],
        get_y=lambda h: h.y,
    )
    if hline_above:
        # Content above the separator constrains top of signature rect
        content_above = nearest_above(
            hline_above.y - 1,
            [l for l in col_tl if l.y1 < hline_above.y - 2],
            get_y=lambda l: l.y1,
        )
        if content_above:
            top = content_above.y1 + PAD
        else:
            top = hline_above.y - MAX_SIG_HEIGHT

        # Never let the rect extend above page or be too tall
        top = max(top, hline_above.y - MAX_SIG_HEIGHT, 0)
        rect = fitz.Rect(x0, top, x1, hline_above.y - PAD)
        if rect.height >= MIN_RECT_HEIGHT:
            return rect

    # ── Option 2: whitespace directly above keyword (no separator line) ──
    content_above = nearest_above(
        match.y0,
        [l for l in col_tl if l.y1 < match.y0 and l is not match],
        get_y=lambda l: l.y1,
    )
    if content_above:
        gap = match.y0 - content_above.y1
        if gap >= MIN_RECT_HEIGHT:
            top = max(content_above.y1 + PAD, match.y0 - MAX_SIG_HEIGHT)
            rect = fitz.Rect(x0, top, x1, match.y0 - PAD)
            if rect.height >= MIN_RECT_HEIGHT:
                return rect

    # ── Option 3: separator below keyword (label-above, space-below pattern) ──
    hline_below = nearest_below(
        match.y1,
        [h for h in col_hl if (h.y - match.y1) <= SEPARATOR_SEARCH_RADIUS],
        get_y=lambda h: h.y,
    )
    if hline_below:
        content_after = nearest_below(
            hline_below.y + 1,
            [l for l in col_tl if l.y0 > hline_below.y + 2],
            get_y=lambda l: l.y0,
        )
        bottom = content_after.y0 - PAD if content_after else hline_below.y + MAX_SIG_HEIGHT
        bottom = min(bottom, hline_below.y + MAX_SIG_HEIGHT)
        rect = fitz.Rect(x0, hline_below.y + PAD, x1, bottom)
        if rect.height >= MIN_RECT_HEIGHT:
            return rect

    return None
