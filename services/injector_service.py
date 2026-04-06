import io
import re
import logging
import fitz
from PIL import Image
from utils.image_utils import SignatureImageProcessor
from utils.pdf_utils import rect_overlaps_text
from utils.text_utils import classify_label

logger = logging.getLogger(__name__)

# ── Constants ────────────────────────────────────────────────
SIGNATURE_PADDING      = 6
MIN_SLOT_HEIGHT        = 30
MIN_GAP_WHITESPACE     = 20
DEBUG_MODE             = False
FALLBACK_ABOVE_DISTANCE = 80
FALLBACK_BELOW_DISTANCE = 60


# ── Main ──────────────────────────────────────────────────────

def inject_signature(pdf_bytes: bytes, signature_path: str,
                     signature_zones: list) -> bytes:
    """
    Inject signatures into PDF at specified zones.

    Primary path  : geometry-based placement via pdf_placer
                    (layout-aware, handles multi-column, no hardcoded logic)
    Fallback path : legacy keyword-scoring (_find_signature_rect)
                    used only if geometry placer returns 0 results

    Public API unchanged — callers (main.py, bot.py) need no modification.
    """
    from services.pdf_placer import place_all_signatures, SignaturePlacement

    sig_bytes = _prepare_signature(signature_path)
    doc       = fitz.open(stream=pdf_bytes, filetype="pdf")

    # Extract keyword: prefer explicit 'keyword' field, fall back to matched_name
    keyword = ""
    if signature_zones:
        keyword = (signature_zones[0].get("keyword")
                   or signature_zones[0].get("matched_name")
                   or "")

    # ── PRIMARY: geometry-based placement ──
    max_count  = len(signature_zones) if signature_zones else None
    placements = place_all_signatures(
        doc, keyword,
        zones_hint=signature_zones,
        max_count=max_count,
    )

    # ── FALLBACK: legacy keyword-scoring (with dedup fix) ──
    if not placements:
        logger.info("[INJ] Geometry placer got 0 results — switching to legacy mode")
        placements = _legacy_place(doc, keyword, signature_zones)

    # ── Insert images ──
    injected_count = 0
    for p in placements:
        logger.info(
            f"[INJ] ✓ [{p.method}] p{p.page.number + 1} "
            f"({p.rect.width:.0f}×{p.rect.height:.0f}pt)"
        )
        if DEBUG_MODE:
            p.page.draw_rect(p.rect, color=(1, 0, 0), width=1)
        _insert_image(p.page, p.rect, sig_bytes)
        injected_count += 1

    if injected_count == 0 and signature_zones:
        doc.close()
        raise Exception(
            f"Gagal inject ke semua zona. Keyword: '{keyword}'"
        )

    buf = io.BytesIO()
    doc.save(buf, deflate=True)
    doc.close()
    return buf.getvalue()


def _legacy_place(doc, keyword: str, zones: list) -> list:
    """
    Legacy per-zone placement using the old keyword+scoring approach.
    Includes deduplication guard: if multiple zones map to the same rect
    (the original 5x-Division-Head bug), only the first instance is kept.
    """
    from services.pdf_placer.types import SignaturePlacement

    placements = []
    seen_rects: set = set()

    for zone in zones:
        name   = zone.get("matched_name") or keyword
        result = _find_signature_rect(doc, name, zone)
        if result is None:
            logger.warning(f"[INJ] ❌ Legacy: gagal detect '{name}'")
            continue

        page, rect, method = result

        # Dedup guard — same rect position means duplicate, skip
        key = (page.number, round(rect.x0), round(rect.y0))
        if key in seen_rects:
            logger.warning(
                f"[INJ] ⚠ Legacy: rect duplikat di p{page.number + 1} "
                f"({rect.x0:.0f},{rect.y0:.0f}), skip"
            )
            continue
        seen_rects.add(key)

        placements.append(SignaturePlacement(
            page=page, rect=rect,
            method=f"legacy_{method}", confidence=0.5,
        ))

    return placements




# ── Core ──────────────────────────────────────────────────────

def _find_signature_rect(doc, name: str, zone: dict = None):
    """
    Cari rect zona TTD dengan context-aware multi-factor scoring.
    
    Strategy:
    1. Kumpulkan semua kandidat match
    2. Tiap kandidat diberi base score (whitespace_above→4, dash_above→3, dll)
    3. Enhance dengan pattern detection, semantic bias, detector hints
    4. Pilih skor tertinggi, tiebreak dengan posisi y terbawah
    """
    zone = zone or {}
    target_words = _words(name)
    candidates = []

    # Semantic classification
    label = classify_label(name)
    preferred = zone.get("inject_position")
    logger.debug(f"[INJ] Classification: {name} → {label}, preferred: {preferred}")

    for page in doc:
        lines = _extract_lines(page)
        if not lines:
            continue

        match_indices = _find_all_name_lines(lines, target_words)

        for match_idx in match_indices:
            name_line = lines[match_idx]
            logger.debug(f"[INJ] MATCH '{name}' @ p{page.number+1} y={name_line['yt']:.0f}")

            # Pattern detection (role→space→name)
            pattern = _detect_layout_pattern(lines, match_idx, name_line)
            if pattern:
                pattern_type, _, pattern_conf = pattern
                logger.debug(f"[INJ]   📊 Pattern: {pattern_type}, confidence={pattern_conf:.2f}")

            # Context-aware method base scores.
            # Prefer placement direction based on semantic label (role vs name).
            # Roles typically have signature BELOW; names often have signature ABOVE.
            if label == "role":
                base_map = {
                    "whitespace_above": 1.0,
                    "dash_above": 0.5,
                    "whitespace_below": 4.0,
                    "dash_below": 3.0,
                }
            elif label == "name":
                base_map = {
                    "whitespace_above": 4.0,
                    "dash_above": 3.0,
                    "whitespace_below": 1.0,
                    "dash_below": 0.5,
                }
            else:
                base_map = {
                    "whitespace_above": 4.0,
                    "dash_above": 3.0,
                    "whitespace_below": 2.0,
                    "dash_below": 1.0,
                }

            methods = [
                ("whitespace_above", _find_slot_above, base_map["whitespace_above"]),
                ("dash_above", _find_dash_above, base_map["dash_above"]),
                ("whitespace_below", _find_slot_below, base_map["whitespace_below"]),
                ("dash_below", _find_dash_below, base_map["dash_below"]),
            ]

            for method_name, fn, base_score in methods:
                rect = fn(lines, match_idx, name_line)
                if rect is None:
                    continue

                has_dash = "dash" in method_name
                
                # Compute available space above and below for spatial heuristic
                space_above = _compute_space_above(lines, match_idx, name_line)
                space_below = _compute_space_below(lines, match_idx, name_line)
                
                score = _calculate_context_aware_score(
                    base_score, method_name, label, has_dash, rect, preferred, pattern,
                    space_above=space_above, space_below=space_below
                )
                candidates.append((page, rect, method_name, score, name_line["yt"]))

            # Fallback
            fallback_rect = fitz.Rect(
                name_line["x0"],
                name_line["yt"] - FALLBACK_ABOVE_DISTANCE,
                name_line["x1"],
                name_line["yt"] - SIGNATURE_PADDING,
            )
            candidates.append(
                (page, _ensure_min_height(fallback_rect), "fallback", 0, name_line["yt"])
            )

    if not candidates:
        return None

    best = max(candidates, key=lambda c: (c[3], c[4]))
    return best[0], best[1], best[2]


# ── Layout Pattern Detection ─────────────────────────────────

def _detect_layout_pattern(lines: list, keyword_idx: int, keyword_line: dict):
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
    tol = (col_x1 - col_x0) * 0.5 + 20
    
    # Ambil baris DIBAWAH dalam kolom yang sama
    lines_below = [
        (i, l) for i, l in enumerate(lines[keyword_idx + 1:], keyword_idx + 1)
        if abs(l["cx"] - col_cx) < tol
    ]
    
    if len(lines_below) < 2:
        return None
    
    # Hitung blank lines berturut-turut dari dibawah keyword
    blank_start_idx = None
    blank_end_idx = None
    content_idx = None
    
    for i, (idx, line) in enumerate(lines_below):
        text = line["text"].strip()
        
        # Blank line?
        if not text:
            if blank_start_idx is None:
                blank_start_idx = idx
            blank_end_idx = idx
        # Content line setelah blanks?
        elif blank_start_idx is not None and blank_end_idx is not None:
            # Ini adalah content line SETELAH blank space
            # Check apakah ini "name-like" (multiple words, mostly text)
            word_count = len(text.split())
            if 1 <= word_count <= 5:  # typical name: 1-5 words
                content_idx = idx
                break
        # Content SEBELUM blank? → pola tidak match
        elif blank_start_idx is None and text:
            break
    
    # Pattern detected: role → blanks → name
    if (blank_start_idx is not None and 
        blank_end_idx is not None and 
        content_idx is not None and
        blank_start_idx >= keyword_idx + 1 and
        blank_end_idx >= blank_start_idx):
        
        # Range untuk inject: antara blank start dan blank end
        blank_count = blank_end_idx - blank_start_idx + 1
        confidence = min(0.95, 0.5 + blank_count * 0.2)  # lebih banyak blank = confidence tinggi
        
        return ("role_space_name", (blank_start_idx, blank_end_idx), confidence)
    
    return None


# ── Scoring Helpers ──────────────────────────────────────────


def _space_score(rect: fitz.Rect) -> float:
    """
    Score kualitas dari space (slot) berdasarkan heightnya.
    
    Semakin lebar space, semakin tinggi score.
    - height > 60 → 2.0 (excellent)
    - height > 40 → 1.0 (good)
    - height ≤ 40 → 0.0 (okay/minimal)
    """
    height = rect.height
    
    if height > 60:
        return 2.0
    elif height > 40:
        return 1.0
    return 0.0


def _compute_space_above(lines: list, keyword_idx: int, keyword_line: dict) -> float:
    """
    Compute available vertical space above the keyword (in points).
    Useful for spatial heuristic.
    """
    col_cx = keyword_line["cx"]
    col_x0 = keyword_line["x0"]
    col_x1 = keyword_line["x1"]
    tol = (col_x1 - col_x0) * 0.5 + 20
    
    col_lines_above = [
        l for l in lines 
        if abs(l["cx"] - col_cx) < tol and l["yt"] < keyword_line["yt"]
    ]
    
    if not col_lines_above:
        return 0.0
    
    nearest_above = max(col_lines_above, key=lambda l: l["yt"])
    return keyword_line["yt"] - nearest_above["yb"]


def _compute_space_below(lines: list, keyword_idx: int, keyword_line: dict) -> float:
    """
    Compute available vertical space below the keyword (in points).
    Useful for spatial heuristic.
    """
    col_cx = keyword_line["cx"]
    col_x0 = keyword_line["x0"]
    col_x1 = keyword_line["x1"]
    tol = (col_x1 - col_x0) * 0.5 + 20
    
    col_lines_below = [
        l for l in lines 
        if abs(l["cx"] - col_cx) < tol and l["yt"] > keyword_line["yb"]
    ]
    
    if not col_lines_below:
        return 0.0
    
    nearest_below = min(col_lines_below, key=lambda l: l["yt"])
    return nearest_below["yt"] - keyword_line["yb"]


def _calculate_context_aware_score(
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
    Hitung final score dengan multi-factor evaluation:
    
    Priority (highest → lowest):
    1. Pattern detection (role→space→name override)
    2. HARD CONSTRAINT: if preferred from high-confidence detector → strongly bias or enforce
    3. Spatial heuristic: if space_above >> space_below, favor above (and vice versa)
    4. Semantic bias (name vs role)
    5. Space quality & dash bonus
    """
    score = base_score
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
    # If preferred is set, assume detector found it with good confidence.
    # Strongly bias (or enforce) placement direction.
    if preferred:
        if preferred == "above_same" and "above" in method:
            detector_bonus = 8.0  # Increased from 3.5
            score += detector_bonus
            breakdown["detector_hard"] = detector_bonus
        elif preferred == "above_prev_row" and "above" in method:
            detector_bonus = 7.0  # Increased from 2.5
            score += detector_bonus
            breakdown["detector_hard"] = detector_bonus
        elif preferred == "below_same" and "below" in method:
            detector_bonus = 8.0  # Increased from 3.5
            score += detector_bonus
            breakdown["detector_hard"] = detector_bonus
        elif preferred == "below_next_row" and "below" in method:
            detector_bonus = 7.0  # Increased from 2.5
            score += detector_bonus
            breakdown["detector_hard"] = detector_bonus
        elif preferred:
            # Penalty for methods that don't match hint
            penalty = -5.0
            score += penalty
            breakdown["detector_penalty"] = penalty

    # ── PRIORITY 3: Spatial heuristic ──
    # If space difference is large, strongly bias
    if space_above is not None and space_below is not None:
        diff = space_below - space_above
        if abs(diff) > 40:  # significant difference
            if diff > 0 and "below" in method:
                spatial_bonus = 3.0
                score += spatial_bonus
                breakdown["spatial"] = spatial_bonus
            elif diff < 0 and "above" in method:
                spatial_bonus = 3.0
                score += spatial_bonus
                breakdown["spatial"] = spatial_bonus
            elif diff > 0 and "above" in method:
                spatial_penalty = -2.0
                score += spatial_penalty
                breakdown["spatial"] = spatial_penalty
            elif diff < 0 and "below" in method:
                spatial_penalty = -2.0
                score += spatial_penalty
                breakdown["spatial"] = spatial_penalty

    # ── PRIORITY 4: Semantic Bias (name vs role) ──
    semantic_bonus = 0
    if label == "name":
        if "above" in method:
            semantic_bonus = 2.0
        elif "below" in method:
            semantic_bonus = -1.0
    elif label == "role":
        if "below" in method:
            semantic_bonus = 2.0
        else:
            semantic_bonus = 1.0
    
    score += semantic_bonus
    if semantic_bonus != 0:
        breakdown["semantic"] = semantic_bonus

    # ── Space quality ──
    space_bonus = _space_score(rect)
    score += space_bonus
    if space_bonus > 0:
        breakdown["space"] = space_bonus

    # ── Dash bonus ──
    dash_bonus = 1.5 if has_dash else 0
    score += dash_bonus
    if dash_bonus > 0:
        breakdown["dash"] = dash_bonus

    if DEBUG_MODE:
        parts = " + ".join(f"{k}={v:.1f}" for k, v in breakdown.items())
        logger.debug(f"[INJ]   {method}: {parts} = {score:.1f}")

    return score


# ── Matching ──────────────────────────────────────────────────

def _find_all_name_lines(lines: list, target_words: list) -> list:
    """
    Temukan semua index baris yang match dengan target_words.
    Return list of int (sorted, unique).
    """
    if not target_words:
        return []

    indices = []

    for i, line in enumerate(lines):
        line_words = _words(line["text"])

        # Full match dalam 1 baris
        if all(tw in line_words for tw in target_words):
            indices.append(i)
            continue

        # Cross-span: 2 baris berurutan berdekatan (gap < 10pt)
        if i < len(lines) - 1:
            gap = lines[i + 1]["yt"] - lines[i]["yb"]
            if gap < 10:
                combined = _words(lines[i]["text"] + " " + lines[i + 1]["text"])
                if all(tw in combined for tw in target_words):
                    indices.append(i + 1)

    return sorted(set(indices))


# ── Slot detection ────────────────────────────────────────────

def _expand_width_if_narrow(col_x0: float, col_x1: float, min_width: float = 200.0) -> tuple[float, float]:
    """
    Symmetrically expand width from center if too narrow to ensure
    there's enough space to properly center the signature horizontally.
    """
    w = col_x1 - col_x0
    if w < min_width:
        cx = (col_x0 + col_x1) / 2
        col_x0 = max(0, cx - (min_width / 2))
        col_x1 = col_x0 + min_width
    return col_x0, col_x1


def _find_slot_above(lines: list, name_idx: int, name_line: dict):
    """
    Cari blank space di atas nama dalam kolom yang sama.

    Perbedaan vs versi lama:
    - Tidak lagi ambil gap TERBESAR (yang bisa menunjuk ke area JSON/header jauh di atas)
    - Ambil gap dari baris TERDEKAT di atas nama
    - Ini memastikan rect benar-benar berada di antara nama dan baris di atasnya
    """
    col_cx = name_line["cx"]
    col_x0 = name_line["x0"]
    col_x1 = name_line["x1"]
    tol    = (col_x1 - col_x0) * 0.5 + 20

    # Ambil baris di atas nama dalam kolom yang sama, sorted terdekat dulu
    col_lines_above = sorted(
        [l for l in lines if abs(l["cx"] - col_cx) < tol
         and l["yt"] < name_line["yt"]],
        key=lambda l: l["yt"],
        reverse=True,   # terdekat (yt terbesar) duluan
    )

    if not col_lines_above:
        return None

    nearest = col_lines_above[0]
    gap     = name_line["yt"] - nearest["yb"]

    if gap < MIN_GAP_WHITESPACE:
        return None

    col_x0, col_x1 = _expand_width_if_narrow(col_x0, col_x1)

    rect = fitz.Rect(
        col_x0,
        nearest["yb"] + SIGNATURE_PADDING,
        col_x1,
        name_line["yt"] - SIGNATURE_PADDING,
    )
    return _ensure_min_height(rect)


def _find_dash_above(lines: list, name_idx: int, name_line: dict):
    """Cari garis --- di atas nama dalam kolom yang sama."""
    col_cx = name_line["cx"]
    col_x0 = name_line["x0"]
    col_x1 = name_line["x1"]
    tol    = (col_x1 - col_x0) * 0.5 + 20

    for line in reversed(lines[:name_idx]):
        if abs(line["cx"] - col_cx) > tol:
            continue
        txt = line["text"].replace(" ", "")
        if len(txt) >= 4 and all(c in "-_" for c in txt):
            col_x0, col_x1 = _expand_width_if_narrow(col_x0, col_x1)
            rect = fitz.Rect(
                col_x0,
                line["yt"] - 80,
                col_x1,
                line["yt"] - SIGNATURE_PADDING,
            )
            return _ensure_min_height(rect)

    return None


def _find_slot_below(lines: list, name_idx: int, name_line: dict):
    """
    Cari blank space di BAWAH nama dalam kolom yang sama.
    Digunakan sebagai fallback ketika slot di atas tidak ditemukan.
    """
    col_cx = name_line["cx"]
    col_x0 = name_line["x0"]
    col_x1 = name_line["x1"]
    tol    = (col_x1 - col_x0) * 0.5 + 20

    col_lines_below = sorted(
        [l for l in lines if abs(l["cx"] - col_cx) < tol
         and l["yt"] > name_line["yb"]],
        key=lambda l: l["yt"],
    )

    if not col_lines_below:
        return None

    nearest = col_lines_below[0]
    gap     = nearest["yt"] - name_line["yb"]

    if gap < MIN_GAP_WHITESPACE:
        return None

    col_x0, col_x1 = _expand_width_if_narrow(col_x0, col_x1)

    rect = fitz.Rect(
        col_x0,
        name_line["yb"] + SIGNATURE_PADDING,
        col_x1,
        nearest["yt"] - SIGNATURE_PADDING,
    )
    return _ensure_min_height(rect)


def _find_dash_below(lines: list, name_idx: int, name_line: dict):
    """Cari garis --- di BAWAH nama dalam kolom yang sama."""
    col_cx = name_line["cx"]
    col_x0 = name_line["x0"]
    col_x1 = name_line["x1"]
    tol    = (col_x1 - col_x0) * 0.5 + 20

    for line in lines[name_idx + 1:]:
        if abs(line["cx"] - col_cx) > tol:
            continue
        txt = line["text"].replace(" ", "")
        if len(txt) >= 4 and all(c in "-_" for c in txt):
            col_x0, col_x1 = _expand_width_if_narrow(col_x0, col_x1)
            rect = fitz.Rect(
                col_x0,
                line["yb"] + SIGNATURE_PADDING,
                col_x1,
                line["yb"] + 80,
            )
            return _ensure_min_height(rect)

    return None


# ── Image insertion ───────────────────────────────────────────

def _insert_image(page, rect: fitz.Rect, sig_bytes: bytes):
    """
    Sisipkan TTD ke dalam rect.
    - Menggunakan SignatureImageProcessor untuk hapus background & auto-crop.
    - Scale proporsional, fit ke 85% zona (tidak melebihi batas)
    - Cap upscale 2x agar TTD tidak blur
    - Bottom-aligned, center horizontal
    - Guard: cy tidak boleh kurang dari rect.y0
    """
    processor = SignatureImageProcessor()
    sig_bytes, iw, ih = processor.process(sig_bytes)

    zone_w = rect.width
    zone_h = rect.height

    # Initial scale (fit to 85% of zone, cap upscale)
    max_scale = min((zone_w * 0.85) / iw, (zone_h * 0.85) / ih, 2.0)
    min_scale = 0.4
    step = 0.1

    inserted = False
    tried_scales = []

    # Try decreasing scales until no text overlap or until min_scale
    s = max_scale
    while s >= min_scale:
        fw = iw * s
        fh = ih * s

        # Center horizontal
        cx = rect.x0 + (zone_w - fw) / 2
        # Bottom-aligned, but ensure not above rect.y0
        cy = max(rect.y0, rect.y1 - fh)

        img_rect = fitz.Rect(cx, cy, cx + fw, cy + fh)
        tried_scales.append(s)

        if not rect_overlaps_text(page, img_rect):
            logger.debug(f"[INJ]   zone={zone_w:.0f}x{zone_h:.0f}pt → img={fw:.0f}x{fh:.0f}pt scale={s:.2f}")
            page.insert_image(img_rect, stream=sig_bytes)
            inserted = True
            break

        s -= step

    if not inserted:
        # Last resort: insert at smallest scale even if overlap (so user still gets PDF)
        s = max(min_scale, min(max_scale, s + step))
        fw = iw * s
        fh = ih * s
        cx = rect.x0 + (zone_w - fw) / 2
        cy = max(rect.y0, rect.y1 - fh)
        logger.debug(f"[INJ]   fallback insert (overlap) scale={s:.2f}, tried={tried_scales}")
        page.insert_image(fitz.Rect(cx, cy, cx + fw, cy + fh), stream=sig_bytes)





# ── Utilities ─────────────────────────────────────────────────

def _extract_lines(page) -> list:
    lines = []
    for block in page.get_text("dict").get("blocks", []):
        if block.get("type") != 0:
            continue
        for line in block.get("lines", []):
            text = " ".join(s["text"] for s in line["spans"]).strip()
            if not text:
                continue
            bbox = line["bbox"]
            lines.append({
                "text": text,
                "yt":   bbox[1],
                "yb":   bbox[3],
                "x0":   bbox[0],
                "x1":   bbox[2],
                "cx":   (bbox[0] + bbox[2]) / 2,
            })
    return sorted(lines, key=lambda l: l["yt"])


def _words(text: str) -> list:
    return re.sub(r"[^a-z0-9\s]", "", text.lower()).split()


def _ensure_min_height(rect: fitz.Rect) -> fitz.Rect:
    if rect.height < MIN_SLOT_HEIGHT:
        rect = fitz.Rect(rect.x0, rect.y1 - MIN_SLOT_HEIGHT, rect.x1, rect.y1)
    return rect


def _prepare_signature(path: str) -> bytes:
    ext = path.rsplit(".", 1)[-1].lower()
    if ext == "svg":
        import cairosvg
        return cairosvg.svg2png(url=path)
    img = Image.open(path).convert("RGBA")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()