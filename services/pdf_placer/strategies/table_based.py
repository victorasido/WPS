# services/pdf_placer/strategies/table_based.py
#
# Handles documents where signature slots are inside table cells defined
# by drawn grid lines (both horizontal + vertical).
#
# Pattern (Document 2 — Developer/Supervisor/Approval table):
#   ┌──────────────┬───────────────────┬──────────────────┐
#   │              │                   │                  │
#   │   [sig here] │                   │                  │
#   │              │                   │                  │
#   │ Farino Joshua│ Muhammad Angga    │ Wildan Anugrah   │
#   └──────────────┴───────────────────┴──────────────────┘

from __future__ import annotations
from typing import List, Optional
import fitz

from ..layout_extractor import PageLayout, TextLine, Column
from ..types import SignaturePlacement
from ..utils.geometry import find_keyword_lines, nearest_above

PAD = 5.0
MIN_RECT_HEIGHT = 20.0
MIN_CELL_HEIGHT = 10.0


def find_placements(
    layout: PageLayout,
    keyword: str,
    page: fitz.Page,
) -> List[SignaturePlacement]:
    """
    For each keyword match, detect which table cell contains it,
    then use the empty space above the keyword text within the cell.
    """
    matches = find_keyword_lines(layout.text_lines, keyword)
    cells   = _detect_cells(page, layout)
    placements = []

    for match in matches:
        cell = _cell_for_line(match, cells)
        if cell is not None:
            rect = _rect_in_cell(match, cell, layout.text_lines)
        else:
            # No cell found — fall back to whitespace above, restricted to column
            col = _find_column(match, layout.columns)
            col_tl = _col_lines(layout.text_lines, col)
            rect = _whitespace_above(match, col_tl)

        if rect is not None and rect.height >= MIN_RECT_HEIGHT:
            placements.append(SignaturePlacement(
                page=page, rect=rect,
                method="table_based", confidence=0.95,
            ))

    return placements


# ── Cell detection ────────────────────────────────────────────

def _detect_cells(page: fitz.Page, layout: PageLayout) -> List[fitz.Rect]:
    """
    Build cell rects from the crossing of horizontal and vertical drawn lines.
    """
    h_ys = sorted({round(h.y) for h in layout.h_lines if h.source == "drawn"})
    v_xs = _extract_v_line_xs(page)

    if len(h_ys) < 2 or len(v_xs) < 2:
        return []

    cells = []
    for i in range(len(h_ys) - 1):
        for j in range(len(v_xs) - 1):
            cell = fitz.Rect(v_xs[j], h_ys[i], v_xs[j + 1], h_ys[i + 1])
            if cell.height >= MIN_CELL_HEIGHT:
                cells.append(cell)
    return cells


def _extract_v_line_xs(page: fitz.Page) -> List[float]:
    """Collect X-midpoints of vertical drawn lines."""
    xs = set()
    for path in page.get_drawings():
        r = path.get("rect")
        if r is None:
            continue
        if r.width <= 3 and r.height > 20:
            xs.add(round((r.x0 + r.x1) / 2))
    return sorted(xs)


# ── Cell ↔ line mapping ───────────────────────────────────────

def _cell_for_line(line: TextLine, cells: List[fitz.Rect]) -> Optional[fitz.Rect]:
    """Return the cell with the largest overlap with this text line."""
    line_rect = fitz.Rect(line.x0, line.y0, line.x1, line.y1)
    best_cell, best_area = None, 0.0
    for cell in cells:
        inter = cell & line_rect
        if inter.is_empty:
            continue
        area = inter.width * inter.height
        if area > best_area:
            best_area = area
            best_cell = cell
    return best_cell


# ── Rect computation ──────────────────────────────────────────

def _rect_in_cell(
    match: TextLine,
    cell: fitz.Rect,
    all_lines: List[TextLine],
) -> Optional[fitz.Rect]:
    """
    Signature rect = space above the keyword text, constrained by cell bounds.
    Other text in the same cell above the keyword sets the top boundary.
    """
    # Lines in same cell, above the keyword match
    lines_above = [
        l for l in all_lines
        if (l is not match
            and l.y1 < match.y0
            and l.x0 >= cell.x0 - 4
            and l.x1 <= cell.x1 + 4)
    ]
    top_y = max((l.y1 for l in lines_above), default=cell.y0)
    top_y = max(top_y, cell.y0)

    rect = fitz.Rect(cell.x0 + PAD, top_y + PAD, cell.x1 - PAD, match.y0 - PAD)
    return rect if rect.height >= MIN_RECT_HEIGHT else None


def _whitespace_above(match: TextLine, col_lines: List[TextLine]) -> Optional[fitz.Rect]:
    """Fallback: empty space directly above match (no cell boundary available)."""
    above = nearest_above(
        match.y0,
        [l for l in col_lines if l.y1 < match.y0 and l is not match],
        get_y=lambda l: l.y1,
    )
    if above and (match.y0 - above.y1) >= MIN_RECT_HEIGHT:
        return fitz.Rect(match.x0, above.y1 + PAD, match.x1, match.y0 - PAD)
    return None


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
