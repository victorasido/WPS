# services/pdf_placer/utils/geometry.py
# Geometric helper functions — keep small, no magic.

from __future__ import annotations
from typing import List, Optional, TypeVar, Callable
import fitz
import difflib

T = TypeVar("T")

# ── Overlap ───────────────────────────────────────────────────

def overlaps(a: fitz.Rect, b: fitz.Rect, margin: float = 2.0) -> bool:
    """True if rects a and b intersect (with optional tolerance margin)."""
    expanded = fitz.Rect(b.x0 - margin, b.y0 - margin,
                         b.x1 + margin, b.y1 + margin)
    return bool(a.intersects(expanded))


def rect_overlaps_text(rect: fitz.Rect, text_lines: list, margin: float = 2.0) -> bool:
    """True if rect visibly overlaps any of the provided text lines."""
    r = fitz.Rect(rect.x0 + margin, rect.y0 + margin, rect.x1 - margin, rect.y1 - margin)
    if r.is_empty:
        return False
    
    for l in text_lines:
        lr = fitz.Rect(l.x0, l.y0, l.x1, l.y1)
        if r.intersects(lr):
            return True
    return False


# ── Neighbour search ──────────────────────────────────────────

def nearest_above(
    target_y: float,
    candidates: List[T],
    get_y: Callable[[T], float],
) -> Optional[T]:
    """Item in candidates with the largest y that is still above target_y."""
    above = [c for c in candidates if get_y(c) < target_y]
    return max(above, key=get_y) if above else None


def nearest_below(
    target_y: float,
    candidates: List[T],
    get_y: Callable[[T], float],
) -> Optional[T]:
    """Item in candidates with the smallest y that is still below target_y."""
    below = [c for c in candidates if get_y(c) > target_y]
    return min(below, key=get_y) if below else None


# ── Column clustering ─────────────────────────────────────────

def cluster_by_x(
    items: List[T],
    get_cx: Callable[[T], float],
    gap: float = 60.0,
) -> List[List[T]]:
    """
    Group items into columns by their X center position.
    Items within 'gap' pts of each other belong to the same column.
    Returns sorted list of groups (each group sorted left-to-right by cx).
    """
    if not items:
        return []
    sorted_items = sorted(items, key=get_cx)
    groups: List[List[T]] = [[sorted_items[0]]]
    for item in sorted_items[1:]:
        if get_cx(item) - get_cx(groups[-1][-1]) > gap:
            groups.append([])
        groups[-1].append(item)
    return groups


# ── Keyword matching ──────────────────────────────────────────

def find_keyword_lines(lines: list, keyword: str) -> list:
    """
    Return all TextLines that match the keyword.

    Match tiers (returns ALL matches, not just first tier):
    - Exact substring (case-insensitive)
    - All words in keyword present (case-insensitive)
    """
    if not keyword or not lines:
        return []

    kw_lower = keyword.lower().strip()
    kw_words = set(kw_lower.split())
    results  = []

    for line in lines:
        text_lower = line.text.lower()
        # Skip lines that are purely separators (dashes/underscores)
        clean = line.text.replace(" ", "")
        if clean and all(c in "-_" for c in clean):
            continue
        if kw_lower in text_lower:
            results.append(line)
        elif kw_words and len(kw_words) >= 2 and all(w in text_lower for w in kw_words):
            results.append(line)
        elif kw_words:
            # Fuzzy match: try to match every keyword word against line words
            line_words = text_lower.split()
            if line_words:
                match_count = sum(
                    1 for w in kw_words
                    if any(difflib.SequenceMatcher(None, w, lw).ratio() > 0.8 for lw in line_words)
                )
                if match_count == len(kw_words):
                    results.append(line)

    return results
