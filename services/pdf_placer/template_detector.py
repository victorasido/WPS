# services/pdf_placer/template_detector.py
# Classify the layout of a page so the right placement strategy is used.

from __future__ import annotations
from enum import Enum
from .layout_extractor import PageLayout


class TemplateType(Enum):
    TABLE_BASED = "table_based"   # Drawn H + V grid lines → cells
    LINE_BASED  = "line_based"    # Dash/drawn H lines without full grid
    FREE_SPACE  = "free_space"    # No clear line structure — use whitespace


def detect_template(layout: PageLayout) -> TemplateType:
    """
    Heuristic page classification.

    Priority:
        1. TABLE_BASED  — drawn grid (H lines + V lines detected)
        2. LINE_BASED   — at least 1 separator line (drawn or text-dash)
        3. FREE_SPACE   — fallback
    """
    if layout.has_grid:
        return TemplateType.TABLE_BASED

    if layout.h_lines:
        return TemplateType.LINE_BASED

    return TemplateType.FREE_SPACE
