"""
services/detector/matchers.py
Algoritma pencocokan teks (keyword matching) untuk deteksi zona TTD.

Berisi 3-tier Match Cascade:
    Tier 1 — Exact, case-sensitive         (confidence 1.0)
    Tier 2 — Full phrase, case-insensitive  (confidence 0.9)
    Tier 3 — Partial per kata (≥60% match) (confidence 0.5–0.9)

Modul ini murni text-matching, tidak bergantung pada format file apapun.
"""

import re
import difflib
from src.shared.text_utils import best_matching_line, classify_label
from .validators import DEFAULT_VALIDATOR


# ── Confidence weights ────────────────────────────────────────

CONF_EXACT        = 1.0
CONF_ICASE        = 0.9
CONF_PARTIAL_BASE = 0.5
CONF_DASH_BONUS   = 0.05

PARTIAL_MIN_RATIO = 0.6


# ── Public API ────────────────────────────────────────────────

def match_cascade(keyword: str, cell_text: str):
    """
    Coba match keyword ke cell_text dengan 3 tier.
    Return (matched_text, confidence) atau None.
    """
    if not keyword or not cell_text.strip():
        return None

    # Semantic Validation: pastikan teks bukan label/key-value
    if not DEFAULT_VALIDATOR.is_valid(cell_text):
        return None

    # Tier 1: exact (case-sensitive)
    if keyword in cell_text:
        return best_matching_line(keyword, cell_text), CONF_EXACT

    # Tier 2: case-insensitive full phrase
    if keyword.lower() in cell_text.lower():
        return best_matching_line(keyword, cell_text), CONF_ICASE

    # Tier 3: partial per kata
    return _partial_match(keyword, cell_text)


# ── Internal Helpers ──────────────────────────────────────────

def _partial_match(keyword: str, cell_text: str):
    """
    Bulletproof 3-Layer Architecture for partial matching:
    1. Exact Token Boundaries: Prevent substring matching ("it" in "auditor").
    2. Strict Role Threshold: If role, require 1.0 (100% matched tokens).
    3. Negative Penalty: Deduct confidence for garbage words.
    """
    kw_words   = [w for w in re.split(r'\W+', keyword.lower()) if w]
    cell_lower = cell_text.lower()
    cell_words = [w for w in re.split(r'\W+', cell_lower) if w]

    if not kw_words or not cell_words:
        return None

    # Layer 1: Strict Token Matching (via exact string eq or difflib)
    matched = []
    for w in kw_words:
        if w in cell_words:
            matched.append(w)
        else:
            # allow slight typo handling (e.g. 1 char diff for long words)
            for cw in cell_words:
                if len(cw) >= 4 and difflib.SequenceMatcher(None, w, cw).ratio() > 0.85:
                    matched.append(w)
                    break

    # Layer 2: Strict Role vs Name Threshold
    label     = classify_label(keyword)
    threshold = 1.0 if label == "role" else PARTIAL_MIN_RATIO

    ratio = len(matched) / len(kw_words)
    if ratio < threshold:
        return None

    # Layer 3: Negative Penalty Tie-Breaker
    extra_words      = len(cell_words) - len(matched)
    penalty          = max(0, extra_words * 0.05)
    base_conf        = CONF_PARTIAL_BASE + ratio * (CONF_ICASE - CONF_PARTIAL_BASE)
    final_confidence = max(0, base_conf - penalty)

    if final_confidence < CONF_PARTIAL_BASE and ratio < 1.0:
        return None

    return best_matching_line(keyword, cell_text), round(final_confidence, 3)
