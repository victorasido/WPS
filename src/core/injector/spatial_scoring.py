"""
core/injector/spatial_scoring.py
Logika berat pencarian koordinat dan scoring zona TTD pada PDF.

Berisi:
- find_all_name_lines   : mencari semua baris yang cocok dengan keyword
- detect_layout_pattern : deteksi pola role→blank→name
- space_score           : scoring kualitas slot berdasarkan height
- compute_space_above   : hitung ruang vertikal di atas keyword
- compute_space_below   : hitung ruang vertikal di bawah keyword
- calculate_context_aware_score : final multi-factor scoring
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

# ── Scoring Constants ────────────────────────────────────────
# Tweak angka-angka ini jika ingin mengubah perilaku penempatan TTD.

# Pattern detection bonus/penalty (Priority 1)
PATTERN_BONUS    = 5.0   # bonus if method matches detected role→space→name pattern
PATTERN_PENALTY  = -3.0  # penalty if method opposes the pattern

# Detector hard constraint bonus/penalty (Priority 2)
DETECTOR_SAME_ROW_BONUS = 8.0   # preferred == "above_same" or "below_same"
DETECTOR_PREV_ROW_BONUS = 7.0   # preferred == "above_prev_row" or "below_next_row"
DETECTOR_MISMATCH_PENALTY = -5.0 # method direction doesn't match preferred

# Spatial heuristic (Priority 3) — triggers when |space_below - space_above| > SPATIAL_THRESHOLD
SPATIAL_THRESHOLD  = 40.0
SPATIAL_BONUS      = 3.0
SPATIAL_PENALTY    = -2.0

# Semantic bias (Priority 4)
SEMANTIC_MATCH_BONUS   = 2.0
SEMANTIC_MISMATCH_BIAS = -1.0
SEMANTIC_NEUTRAL_ROLE  = 1.0   # role label: "below" also gets a small bonus

# Space quality thresholds
SPACE_EXCELLENT_H  = 60.0   # height > this → score 2.0
SPACE_GOOD_H       = 40.0   # height > this → score 1.0
SPACE_SCORE_EXCELLENT = 2.0
SPACE_SCORE_GOOD      = 1.0

# Dash bonus
DASH_BONUS = 1.5

# Column tolerance base (added to half-width of keyword line)
COLUMN_TOL_BASE = 20.0

# Cross-span max gap between adjacent lines (pt)
CROSS_SPAN_MAX_GAP = 10.0

# Layout pattern: max word count for "name" text after a blank
PATTERN_NAME_MAX_WORDS = 5

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

    target_pages = [zone.get("page_num")] if zone and zone.get("page_num") is not None else range(len(doc))
    
    for page_num in target_pages:
        page = doc[page_num]
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
            if gap < CROSS_SPAN_MAX_GAP:
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
    tol    = (col_x1 - col_x0) * 0.5 + COLUMN_TOL_BASE

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
            if 1 <= word_count <= PATTERN_NAME_MAX_WORDS:
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
    if h > SPACE_EXCELLENT_H:
        return SPACE_SCORE_EXCELLENT
    elif h > SPACE_GOOD_H:
        return SPACE_SCORE_GOOD
    return 0.0


def compute_space_above(lines: list, keyword_idx: int, keyword_line: dict) -> float:
    """Hitung ruang vertikal yang tersedia di atas keyword (dalam poin)."""
    col_cx = keyword_line["cx"]
    col_x0 = keyword_line["x0"]
    col_x1 = keyword_line["x1"]
    tol    = (col_x1 - col_x0) * 0.5 + COLUMN_TOL_BASE

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
    tol    = (col_x1 - col_x0) * 0.5 + COLUMN_TOL_BASE

    col_lines_below = [
        l for l in lines
        if abs(l["cx"] - col_cx) < tol and l["yt"] > keyword_line["yb"]
    ]

    if not col_lines_below:
        return 0.0

    nearest_below = min(col_lines_below, key=lambda l: l["yt"])
    return nearest_below["yt"] - keyword_line["yb"]


def _apply_pattern_strategy(method: str, pattern: tuple) -> tuple[float, float]:
    """PRIORITY 1: Pattern Detection Strategy"""
    if pattern is None:
        return 0.0, 0.0
    
    pattern_type, _, pattern_conf = pattern
    if pattern_type == "role_space_name":
        if "below" in method:
            return PATTERN_BONUS * pattern_conf, PATTERN_BONUS * pattern_conf
        elif "above" in method:
            return PATTERN_PENALTY * pattern_conf, PATTERN_PENALTY * pattern_conf
            
    return 0.0, 0.0


def _apply_detector_strategy(method: str, preferred: str) -> float:
    """PRIORITY 2: Hard Constraint from detector"""
    if not preferred:
        return 0.0
        
    if preferred == "above_same" and "above" in method:
        return DETECTOR_SAME_ROW_BONUS
    elif preferred == "above_prev_row" and "above" in method:
        return DETECTOR_PREV_ROW_BONUS
    elif preferred == "below_same" and "below" in method:
        return DETECTOR_SAME_ROW_BONUS
    elif preferred == "below_next_row" and "below" in method:
        return DETECTOR_PREV_ROW_BONUS
    else:
        return DETECTOR_MISMATCH_PENALTY


def _apply_spatial_strategy(method: str, space_above: float, space_below: float) -> float:
    """PRIORITY 3: Spatial heuristic Strategy"""
    if space_above is None or space_below is None:
        return 0.0
        
    diff = space_below - space_above
    if abs(diff) > SPATIAL_THRESHOLD:
        if diff > 0 and "below" in method:
            return SPATIAL_BONUS
        elif diff < 0 and "above" in method:
            return SPATIAL_BONUS
        elif diff > 0 and "above" in method:
            return SPATIAL_PENALTY
        elif diff < 0 and "below" in method:
            return SPATIAL_PENALTY
    return 0.0


def _apply_semantic_strategy(method: str, label: str) -> float:
    """PRIORITY 4: Semantic Bias Strategy"""
    if label == "name":
        return SEMANTIC_MATCH_BONUS if "above" in method else SEMANTIC_MISMATCH_BIAS
    elif label == "role":
        return SEMANTIC_MATCH_BONUS if "below" in method else SEMANTIC_NEUTRAL_ROLE
    return 0.0


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
    Hitung final score dengan pipeline Strategy Pattern.
    """
    score = base_score
    breakdown = {"base": base_score}

    # 1. Pattern Strategy (Highest Priority - Can override)
    pattern_score, override_val = _apply_pattern_strategy(method, pattern)
    if override_val != 0.0:
        score += override_val
        breakdown["pattern"] = override_val
        if DEBUG_MODE:
            logger.debug(f"[INJ]   Pattern override: {override_val:.1f}")
        return score

    # 2. Detector Strategy
    det_score = _apply_detector_strategy(method, preferred)
    if det_score:
        score += det_score
        breakdown["detector"] = det_score

    # 3. Spatial Strategy
    spat_score = _apply_spatial_strategy(method, space_above, space_below)
    if spat_score:
        score += spat_score
        breakdown["spatial"] = spat_score

    # 4. Semantic Strategy
    sem_score = _apply_semantic_strategy(method, label)
    if sem_score:
        score += sem_score
        breakdown["semantic"] = sem_score

    # 5. Base Space & Dash Boost
    sq = space_score(rect)
    if sq:
        score += sq
        breakdown["space"] = sq

    db = DASH_BONUS if has_dash else 0
    if db:
        score += db
        breakdown["dash"] = db

    if DEBUG_MODE:
        parts = " + ".join(f"{k}={v:.1f}" for k, v in breakdown.items())
        logger.debug(f"[INJ]   {method}: {parts} = {score:.1f}")

    return score
