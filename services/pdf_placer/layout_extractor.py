# services/pdf_placer/layout_extractor.py
# Extract geometric features from a PDF page:
#   text lines, horizontal separator lines, column clusters.

from __future__ import annotations
import re
from dataclasses import dataclass, field
from typing import List, Tuple
import fitz

from .utils.geometry import cluster_by_x

# A text line that looks like "--------" or "________"
_DASH_RE = re.compile(r"^[-_\s]{4,}$")

# Minimum line width as fraction of page width to count as a separator
_HLINE_MIN_WIDTH_RATIO = 0.08

# Maximum drawn-line height to be considered "horizontal"
_HLINE_MAX_THICKNESS = 3.0

# Minimum gap in X between two text groups to be separate columns
_COLUMN_GAP = 55.0


# ── Data classes ──────────────────────────────────────────────

@dataclass
class TextLine:
    text: str
    x0: float
    y0: float
    x1: float
    y1: float

    @property
    def cx(self) -> float:      return (self.x0 + self.x1) / 2
    @property
    def cy(self) -> float:      return (self.y0 + self.y1) / 2
    @property
    def width(self) -> float:   return self.x1 - self.x0
    @property
    def height(self) -> float:  return self.y1 - self.y0


@dataclass
class HLine:
    """Horizontal separator line — either a drawn PDF element or text dashes."""
    x0:     float
    x1:     float
    y:      float
    source: str   # "drawn" | "text_dash"

    @property
    def cx(self) -> float:    return (self.x0 + self.x1) / 2
    @property
    def width(self) -> float: return self.x1 - self.x0


@dataclass
class Column:
    """A vertical band of the page determined by X clustering."""
    x_min: float
    x_max: float

    @property
    def cx(self) -> float:    return (self.x_min + self.x_max) / 2
    @property
    def width(self) -> float: return self.x_max - self.x_min

    def contains_x(self, x: float, margin: float = 12.0) -> bool:
        return self.x_min - margin <= x <= self.x_max + margin


@dataclass
class PageLayout:
    page_width:  float
    page_height: float
    text_lines:  List[TextLine] = field(default_factory=list)
    h_lines:     List[HLine]   = field(default_factory=list)
    columns:     List[Column]  = field(default_factory=list)
    has_grid:    bool          = False   # True → drawn H + V lines (table)


# ── Main entry point ──────────────────────────────────────────

def extract_page_layout(page: fitz.Page) -> PageLayout:
    """Extract all layout features from a single PDF page."""
    rect   = page.rect
    layout = PageLayout(page_width=rect.width, page_height=rect.height)

    layout.text_lines        = _extract_text_lines(page)
    drawn_h, layout.has_grid = _extract_drawn_hlines(page, rect.width)
    dash_h                   = _detect_dash_lines(layout.text_lines)
    layout.h_lines           = drawn_h + dash_h
    layout.columns           = _detect_columns(layout.text_lines, rect.width)

    return layout


# ── Text lines ────────────────────────────────────────────────

def _extract_text_lines(page: fitz.Page) -> List[TextLine]:
    lines = []
    for block in page.get_text("dict").get("blocks", []):
        if block.get("type") != 0:
            continue
        for line in block.get("lines", []):
            text = " ".join(s["text"] for s in line.get("spans", [])).strip()
            if not text:
                continue
            b = line["bbox"]
            lines.append(TextLine(text=text, x0=b[0], y0=b[1], x1=b[2], y1=b[3]))
    return sorted(lines, key=lambda l: l.y0)


# ── Separator lines ───────────────────────────────────────────

def _extract_drawn_hlines(
    page: fitz.Page,
    page_width: float,
) -> Tuple[List[HLine], bool]:
    """
    Extract horizontal lines from PDF drawing paths.
    Also detect if vertical lines exist (grid indicator).
    Returns (h_lines, has_grid).
    """
    h_lines: List[HLine] = []
    has_v = False
    min_w = page_width * _HLINE_MIN_WIDTH_RATIO

    for path in page.get_drawings():
        r = path.get("rect")
        if r is None:
            continue
        w, h = r.width, r.height

        if h <= _HLINE_MAX_THICKNESS and w >= min_w:
            h_lines.append(HLine(
                x0=r.x0, x1=r.x1,
                y=(r.y0 + r.y1) / 2,
                source="drawn",
            ))
        if w <= _HLINE_MAX_THICKNESS and h > 20:
            has_v = True

    has_grid = len(h_lines) >= 2 and has_v
    return h_lines, has_grid


def _detect_dash_lines(text_lines: List[TextLine]) -> List[HLine]:
    """Text lines that are entirely dashes/underscores act as separators."""
    result = []
    for line in text_lines:
        clean = line.text.replace(" ", "")
        if len(clean) >= 4 and _DASH_RE.match(clean):
            result.append(HLine(
                x0=line.x0, x1=line.x1,
                y=(line.y0 + line.y1) / 2,
                source="text_dash",
            ))
    return result


# ── Column detection ──────────────────────────────────────────

def _detect_columns(text_lines: List[TextLine], page_width: float) -> List[Column]:
    """Cluster text lines by X center to discover document columns."""
    non_dash = [
        l for l in text_lines
        if not (len(l.text.replace(" ", "")) >= 4
                and _DASH_RE.match(l.text.replace(" ", "")))
    ]
    if not non_dash:
        return [Column(x_min=0, x_max=page_width)]

    groups = cluster_by_x(non_dash, get_cx=lambda l: l.cx, gap=_COLUMN_GAP)
    columns = []
    for group in groups:
        x_min = min(l.x0 for l in group)
        x_max = max(l.x1 for l in group)
        columns.append(Column(x_min=x_min, x_max=x_max))
    return columns
