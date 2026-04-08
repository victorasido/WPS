"""
services/injector/legacy_scorer.py
Logika berat pencarian koordinat dan scoring zona TTD pada PDF.

Berisi:
- _find_all_name_lines : mencari semua baris yang cocok dengan keyword
- _detect_layout_pattern: deteksi pola role→blank→name
- _space_score          : scoring kualitas slot berdasarkan height
- _compute_space_above  : hitung ruang vertikal di atas keyword
- _compute_space_below  : hitung ruang vertikal di bawah keyword
- _calculate_context_aware_score : final multi-factor scoring
- find_signature_rect   : fungsi utama — cari rect terbaik untuk TTD

Modul ini bergantung pada scanners.py untuk operasi geometri level rendah.
"""

import logging
import fitz
from src.shared.text_utils import classify_label
from .scanners import (
    extract_lines,
    words,
    ensure_min_height,
    find_slot_above,
    find_dash_above,
    find_slot_below,
    find_dash_below,
    SIGNATURE_PADDING,
    FALLBACK_ABOVE_DISTANCE,
    DEBUG_MODE,
)

logger = logging.getLogger(__name__)


# ── Public API ────────────────────────────────────────────────

def find_signature_rect(doc, name: str, zone: dict = None):
    """
    Cari rect zona TTD dengan context-aware multi-factor scoring.

    Strategy:
    1. Kumpulkan semua kandidat match dari seluruh halaman
    2. Tiap kandidat diberi base score (whitespace_above→4, dash_above→3, dll)
    3. Enhance dengan pattern detection, semantic bias, detector hints
    4. Pilih skor tertinggi, tiebreak dengan posisi y terbawah
    """
    zone         = zone or {}
    target_words = words(name)
    candidates   = []

    # Semantic classification
    label     = classify_label(name)
    preferred = zone.get("inject_position")
    logger.debug(f"[INJ] Classification: {name} → {label}, preferred: {preferred}")

    for page in doc:
        lines = extract_lines(page)
        if not lines:
            continue

        match_indices = find_all_name_lines(lines, target_words)

        for match_idx in match_indices:
            name_line = lines[match_idx]
            logger.debug(f"[INJ] MATCH '{name}' @ p{page.number+1} y={name_line['yt']:.0f}")

            # Pattern detection (role→space→name)
            pattern = detect_layout_pattern(lines, match_idx, name_line)
            if pattern:
                pattern_type, _, pattern_conf = pattern
                logger.debug(f"[INJ]   📊 Pattern: {pattern_type}, confidence={pattern_conf:.2f}")

            # Context-aware method base scores.
            # Prefer placement direction based on semantic label (role vs name).
            if label == "role":
                base_map = {
                    "whitespace_above": 1.0,
                    "dash_above":       0.5,
                    "whitespace_below": 4.0,
                    "dash_below":       3.0,
                }
            elif label == "name":
                base_map = {
                    "whitespace_above": 4.0,
                    "dash_above":       3.0,
                    "whitespace_below": 1.0,
                    "dash_below":       0.5,
                }
            else:
                base_map = {
                    "whitespace_above": 4.0,
                    "dash_above":       3.0,
                    "whitespace_below": 2.0,
                    "dash_below":       1.0,
                }

            method_fns = [
                ("whitespace_above", find_slot_above,  base_map["whitespace_above"]),
                ("dash_above",       find_dash_above,  base_map["dash_above"]),
                ("whitespace_below", find_slot_below,  base_map["whitespace_below"]),
                ("dash_below",       find_dash_below,  base_map["dash_below"]),
            ]

            for method_name, fn, base_score in method_fns:
                rect = fn(lines, match_idx, name_line)
                if rect is None:
                    continue

                has_dash    = "dash" in method_name
                space_above = compute_space_above(lines, match_idx, name_line)
                space_below = compute_space_below(lines, match_idx, name_line)

                score = calculate_context_aware_score(
                    base_score, method_name, label, has_dash, rect, preferred, pattern,
                    space_above=space_above, space_below=space_below,
                )
                candidates.append((page, rect, method_name, score, name_line["yt"]))

            # Fallback rect (score 0 — last resort)
            fallback_rect = fitz.Rect(
                name_line["x0"],
                name_line["yt"] - FALLBACK_ABOVE_DISTANCE,
                name_line["x1"],
                name_line["yt"] - SIGNATURE_PADDING,
            )
            candidates.append(
                (page, ensure_min_height(fallback_rect), "fallback", 0, name_line["yt"])
            )

    if not candidates:
        return None

    best = max(candidates, key=lambda c: (c[3], c[4]))
    return best[0], best[1], best[2]


# ── Name Line Finder ──────────────────────────────────────────

def find_all_name_lines(lines: list, target_words: list) -> list:
    """
    Temukan semua index baris yang match dengan target_words.
    Mendukung full-match dalam 1 baris dan cross-span 2 baris berdekatan.
    Return list of int (sorted, unique).
    """
    if not target_words:
        return []

    indices = []

    for i, line in enumerate(lines):
        line_words = words(line["text"])

        # Full match dalam 1 baris
        if all(tw in line_words for tw in target_words):
            indices.append(i)
            continue

        # Cross-span: 2 baris berurutan berdekatan (gap < 10pt)
        if i < len(lines) - 1:
            gap = lines[i + 1]["yt"] - lines[i]["yb"]
            if gap < 10:
                combined = words(lines[i]["text"] + " " + lines[i + 1]["text"])
                if all(tw in combined for tw in target_words):
                    indices.append(i + 1)

    return sorted(set(indices))


# ── Layout Pattern Detection ──────────────────────────────────

def detect_layout_pattern(lines: list, keyword_idx: int, keyword_line: dict):
    """
    Deteksi apakah keyword mengikuti pola struktur tertentu.

    POLA: Role → Blank Space → Name
    Contoh:
        Developer           ← keyword (index 0)
        [blank space]       ← index 1
        [blank space]       ← index 2
        Farino Joshua       ← index 3, nama

    Return:
        ("role_space_name", below_slot_range, confidence)
        atau None jika pola tidak terdeteksi
    """
    if keyword_idx >= len(lines) - 2:
        return None

    col_cx = keyword_line["cx"]
    col_x0 = keyword_line["x0"]
    col_x1 = keyword_line["x1"]
    tol    = (col_x1 - col_x0) * 0.5 + 20

    # Ambil baris DIBAWAH dalam kolom yang sama
    lines_below = [
        (i, l) for i, l in enumerate(lines[keyword_idx + 1:], keyword_idx + 1)
        if abs(l["cx"] - col_cx) < tol
    ]

    if len(lines_below) < 2:
        return None

    blank_start_idx = None
    blank_end_idx   = None
    content_idx     = None

    for _, (idx, line) in enumerate(lines_below):
        text = line["text"].strip()

        if not text:
            if blank_start_idx is None:
                blank_start_idx = idx
            blank_end_idx = idx
        elif blank_start_idx is not None and blank_end_idx is not None:
            word_count = len(text.split())
            if 1 <= word_count <= 5:  # typical name: 1-5 words
                content_idx = idx
                break
        elif blank_start_idx is None and text:
            break

    if (blank_start_idx is not None and
            blank_end_idx is not None and
            content_idx is not None and
            blank_start_idx >= keyword_idx + 1 and
            blank_end_idx >= blank_start_idx):

        blank_count = blank_end_idx - blank_start_idx + 1
        confidence  = min(0.95, 0.5 + blank_count * 0.2)
        return ("role_space_name", (blank_start_idx, blank_end_idx), confidence)

    return None


# ── Scoring Helpers ───────────────────────────────────────────

def space_score(rect: fitz.Rect) -> float:
    """
    Score kualitas dari space (slot) berdasarkan height.
    - height > 60 → 2.0 (excellent)
    - height > 40 → 1.0 (good)
    - height ≤ 40 → 0.0 (minimal)
    """
    h = rect.height
    if h > 60:
        return 2.0
    elif h > 40:
        return 1.0
    return 0.0


def compute_space_above(lines: list, keyword_idx: int, keyword_line: dict) -> float:
    """Hitung ruang vertikal yang tersedia di atas keyword (dalam poin)."""
    col_cx = keyword_line["cx"]
    col_x0 = keyword_line["x0"]
    col_x1 = keyword_line["x1"]
    tol    = (col_x1 - col_x0) * 0.5 + 20

    col_lines_above = [
        l for l in lines
        if abs(l["cx"] - col_cx) < tol and l["yt"] < keyword_line["yt"]
    ]

    if not col_lines_above:
        return 0.0

    nearest_above = max(col_lines_above, key=lambda l: l["yt"])
    return keyword_line["yt"] - nearest_above["yb"]


def compute_space_below(lines: list, keyword_idx: int, keyword_line: dict) -> float:
    """Hitung ruang vertikal yang tersedia di bawah keyword (dalam poin)."""
    col_cx = keyword_line["cx"]
    col_x0 = keyword_line["x0"]
    col_x1 = keyword_line["x1"]
    tol    = (col_x1 - col_x0) * 0.5 + 20

    col_lines_below = [
        l for l in lines
        if abs(l["cx"] - col_cx) < tol and l["yt"] > keyword_line["yb"]
    ]

    if not col_lines_below:
        return 0.0

    nearest_below = min(col_lines_below, key=lambda l: l["yt"])
    return nearest_below["yt"] - keyword_line["yb"]


def calculate_context_aware_score(
    base_score: float,
    method: str,
    label: str,
    has_dash: bool,
    rect: fitz.Rect,
    preferred: str,
    pattern: tuple = None,
    space_above: float = None,
    space_below: float = None,
) -> float:
    """
    Hitung final score dengan multi-factor evaluation.

    Priority (highest → lowest):
    1. Pattern detection (role→space→name override)
    2. HARD CONSTRAINT: if preferred from high-confidence detector
    3. Spatial heuristic: space_above vs space_below
    4. Semantic bias (name vs role)
    5. Space quality & dash bonus
    """
    score     = base_score
    breakdown = {"base": base_score}

    # ── PRIORITY 1: Pattern Detection (override everything) ──
    if pattern is not None:
        pattern_type, _, pattern_conf = pattern
        if pattern_type == "role_space_name":
            if "below" in method:
                bonus = 5.0 * pattern_conf
                score += bonus
                breakdown["pattern"] = bonus
            elif "above" in method:
                penalty = -3.0 * pattern_conf
                score += penalty
                breakdown["pattern"] = penalty
            if DEBUG_MODE:
                logger.debug(f"[INJ]   Pattern override: {breakdown.get('pattern', 0):.1f}")
            return score

    # ── PRIORITY 2: HARD CONSTRAINT from high-confidence detector ──
    if preferred:
        if preferred == "above_same" and "above" in method:
            bonus = 8.0
        elif preferred == "above_prev_row" and "above" in method:
            bonus = 7.0
        elif preferred == "below_same" and "below" in method:
            bonus = 8.0
        elif preferred == "below_next_row" and "below" in method:
            bonus = 7.0
        else:
            bonus = -5.0  # penalty for mismatched direction

        score += bonus
        breakdown["detector_hard"] = bonus

    # ── PRIORITY 3: Spatial heuristic ──
    if space_above is not None and space_below is not None:
        diff = space_below - space_above
        if abs(diff) > 40:
            if diff > 0 and "below" in method:
                spatial = 3.0
            elif diff < 0 and "above" in method:
                spatial = 3.0
            elif diff > 0 and "above" in method:
                spatial = -2.0
            elif diff < 0 and "below" in method:
                spatial = -2.0
            else:
                spatial = 0.0
            score += spatial
            if spatial != 0:
                breakdown["spatial"] = spatial

    # ── PRIORITY 4: Semantic Bias ──
    if label == "name":
        semantic = 2.0 if "above" in method else -1.0
    elif label == "role":
        semantic = 2.0 if "below" in method else 1.0
    else:
        semantic = 0.0

    score += semantic
    if semantic:
        breakdown["semantic"] = semantic

    # ── Space quality & dash bonus ──
    sq = space_score(rect)
    score += sq
    if sq:
        breakdown["space"] = sq

    db = 1.5 if has_dash else 0
    score += db
    if db:
        breakdown["dash"] = db

    if DEBUG_MODE:
        parts = " + ".join(f"{k}={v:.1f}" for k, v in breakdown.items())
        logger.debug(f"[INJ]   {method}: {parts} = {score:.1f}")

    return score
