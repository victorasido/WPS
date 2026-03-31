# detector_service.py
# Deteksi zona TTD berdasarkan keyword dari nama file TTD
#
# Strategy: match cascade (exact → case-insensitive → partial)
#           lalu validasi slot (blank space di atas/bawah keyword)
#
# Fix utama vs versi lama:
#   - Iterasi tabel via XML langsung (tbl→tr→tc) bukan row.cells
#     → row.cells di python-docx return tc yang salah untuk tabel tertentu
#     → menyebabkan cell valid di-skip karena dianggap merged duplicate
#   - seen_cell_ids sekarang track tc XML element id yang benar
#   - _find_slot sekarang pakai XML rows bukan table.rows untuk akses prev/next row

import os
import re
from docx import Document
from docx.oxml.ns import qn
from core.config import (
    CONFIDENCE_THRESHOLD,
    LAST_PAGES_SCAN,
    IGNORED_LINES,
    DASH_LINE_MIN,
)

# ── Confidence weights ────────────────────────────────────────
CONF_EXACT        = 1.0
CONF_ICASE        = 0.9
CONF_PARTIAL_BASE = 0.5
CONF_DASH_BONUS   = 0.05

PARTIAL_MIN_RATIO = 0.6


def detect_signature_zones(
    docx_path: str,
    signature_path: str,
    confidence_threshold: float = None,
    last_pages: int = None,
) -> list:
    """
    Scan DOCX dan return list zona TTD berdasarkan keyword dari nama file TTD.

    Keyword = nama file tanpa ekstensi.
    Contoh: "Farino.png"                  → keyword: "Farino"
            "Division Head Divisi IT.png"  → keyword: "Division Head Divisi IT"

    Match cascade (stop di tier pertama yang hit):
        Tier 1 — exact, case-sensitive         → confidence 1.0
        Tier 2 — full phrase, case-insensitive → confidence 0.9
        Tier 3 — partial per kata (≥60% match) → confidence 0.5–0.85

    Slot validation (inject point):
        Priority: blank above same cell → blank above prev row
        Fallback:  blank below same cell → blank below next row
        Skip jika tidak ada blank space sama sekali.
    """
    if confidence_threshold is None:
        confidence_threshold = CONFIDENCE_THRESHOLD
    if last_pages is None:
        last_pages = LAST_PAGES_SCAN

    keyword = _extract_keyword(signature_path)
    doc     = Document(docx_path)
    zones   = []

    for t_idx, table in enumerate(doc.tables):
        tbl_xml  = table._tbl
        xml_rows = tbl_xml.findall(qn("w:tr"))

        # seen list pakai identity check (tc is x) — id() Python bisa recycle memori
        seen_tcs: list = []

        for r_idx, tr in enumerate(xml_rows):
            xml_cells = tr.findall(qn("w:tc"))

            for c_idx, tc in enumerate(xml_cells):
                if any(tc is s for s in seen_tcs):
                    continue
                seen_tcs.append(tc)

                cell_text = _tc_text(tc)

                # Phase 1: match cascade
                match_result = _match_cascade(keyword, cell_text)
                if match_result is None:
                    continue

                matched_text, confidence = match_result

                # Phase 2: validate slot
                slot = _find_slot_xml(tc, xml_rows, r_idx, c_idx)

                if slot is not None:
                    inject_p_idx, inject_position, has_dash = slot
                else:
                    # Tidak ada blank space → skip
                    continue

                # Bonus confidence jika ada garis ---
                if has_dash:
                    confidence = min(1.0, confidence + CONF_DASH_BONUS)

                # Filter threshold
                if confidence < confidence_threshold:
                    continue

                # Resolve inject row index
                if inject_position == "above_prev_row":
                    inject_r_idx = r_idx - 1
                elif inject_position == "below_next_row":
                    inject_r_idx = r_idx + 1
                else:
                    inject_r_idx = r_idx

                zones.append({
                    "source":          "table",
                    "paragraph_index": 10000 + t_idx * 1000 + r_idx * 10 + c_idx,
                    "table_location":  (t_idx, inject_r_idx, c_idx, inject_p_idx),
                    "matched_name":    matched_text.strip(),
                    "keyword":         keyword,
                    "confidence":      round(confidence, 2),
                    "context":         cell_text.strip()[:80],
                    "inject_position": inject_position,
                })

    zones.sort(key=lambda z: z["paragraph_index"])
    return zones


# ── XML helpers ───────────────────────────────────────────────

def _tc_text(tc) -> str:
    """Ambil semua teks dari XML tc element."""
    # Preserve paragraph boundaries by joining paragraph texts with newlines.
    paras = _tc_paragraphs(tc)
    return "\n".join(_para_text(p) for p in paras)


def _tc_paragraphs(tc) -> list:
    """Return list of w:p elements dalam tc."""
    return tc.findall(qn("w:p"))


def _para_text(p) -> str:
    """Ambil teks dari satu w:p element."""
    runs = p.findall(".//" + qn("w:t"))
    return "".join(r.text or "" for r in runs)


def _is_tc_blank(tc) -> bool:
    """Cell kosong jika semua paragrafnya tidak punya teks."""
    return all(not _para_text(p).strip() for p in _tc_paragraphs(tc))


def _has_dash_in_tc(tc) -> bool:
    return any(_is_dash_line(_para_text(p)) for p in _tc_paragraphs(tc))


# ── Phase 1: Match cascade ────────────────────────────────────

def _match_cascade(keyword: str, cell_text: str):
    """
    Coba match keyword ke cell_text dengan 3 tier.
    Return (matched_text, confidence) atau None.
    """
    if not keyword or not cell_text.strip():
        return None

    # Tier 1: exact (case-sensitive)
    if keyword in cell_text:
        return _best_matching_line(keyword, cell_text), CONF_EXACT

    # Tier 2: case-insensitive full phrase
    if keyword.lower() in cell_text.lower():
        return _best_matching_line(keyword, cell_text), CONF_ICASE

    # Tier 3: partial per kata
    return _partial_match(keyword, cell_text)


def _partial_match(keyword: str, cell_text: str):
    """
    Min 60% kata dari keyword harus ada di cell_text.
    Confidence range: ~0.5 (60%) hingga ~0.85 (99%).
    """
    kw_words   = keyword.lower().split()
    cell_lower = cell_text.lower()

    if not kw_words:
        return None

    matched = [w for w in kw_words if w in cell_lower]
    ratio   = len(matched) / len(kw_words)

    if ratio < PARTIAL_MIN_RATIO:
        return None

    confidence = CONF_PARTIAL_BASE + ratio * (CONF_ICASE - CONF_PARTIAL_BASE)
    return _best_matching_line(keyword, cell_text), round(confidence, 3)


# ── Phase 2: Slot validation (XML-based) ─────────────────────

def _find_slot_xml(tc, xml_rows: list, r_idx: int, c_idx: int):
    """
    Cari blank space di sekitar cell yang mengandung keyword.
    Semua operasi via XML element langsung — menghindari bug row.cells.

    Priority:
        1. Blank para di atas dalam cell yang sama
        2. Cell r-1 (prev row, same column) kosong
        3. Blank para di bawah dalam cell yang sama
        4. Cell r+1 (next row, same column) kosong

    Return (inject_p_idx, inject_position, has_dash) atau None.
    """
    paras = _tc_paragraphs(tc)

    # 1. Blank para di atas dalam cell yang sama
    result = _blank_above_in_paras(paras)
    if result is not None:
        inject_p_idx, has_dash = result
        return inject_p_idx, "above_same", has_dash

    # 2. Prev row, same column
    if r_idx > 0:
        prev_tc = _get_tc(xml_rows, r_idx - 1, c_idx)
        if prev_tc is not None and _is_tc_blank(prev_tc):
            has_dash = _has_dash_in_tc(tc)
            n_paras  = len(_tc_paragraphs(prev_tc))
            return max(0, n_paras - 1), "above_prev_row", has_dash


    # 3. Blank para di bawah dalam cell yang sama
    result = _blank_below_in_paras(paras)
    if result is not None:
        inject_p_idx, has_dash = result
        return inject_p_idx, "below_same", has_dash

    # 4. Next row, same column
    if r_idx < len(xml_rows) - 1:
        next_tc = _get_tc(xml_rows, r_idx + 1, c_idx)
        if next_tc is not None and len(_tc_paragraphs(next_tc)) >= 0 and _is_tc_blank(next_tc):
            has_dash = _has_dash_in_tc(tc)
            return 0, "below_next_row", has_dash

    return None


def _get_tc(xml_rows: list, r_idx: int, c_idx: int):
    """Ambil tc XML element di posisi (r_idx, c_idx). Return None jika out of range."""
    if r_idx < 0 or r_idx >= len(xml_rows):
        return None
    cells = xml_rows[r_idx].findall(qn("w:tc"))
    if c_idx < 0 or c_idx >= len(cells):
        return None
    return cells[c_idx]


def _blank_above_in_paras(paras: list):
    """
    Cari blank para terakhir sebelum teks pertama.
    Return (inject_p_idx, has_dash) atau None.
    """
    first_text_idx = next(
        (i for i, p in enumerate(paras) if _para_text(p).strip()),
        None
    )
    if first_text_idx is None or first_text_idx == 0:
        return None

    has_dash = any(
        _is_dash_line(_para_text(paras[i]))
        for i in range(first_text_idx)
    )
    return first_text_idx - 1, has_dash


def _blank_below_in_paras(paras: list):
    """
    Cari blank para pertama setelah teks terakhir.
    Return (inject_p_idx, has_dash) atau None.
    """
    last_text_idx = None
    for i in range(len(paras) - 1, -1, -1):
        if _para_text(paras[i]).strip():
            last_text_idx = i
            break

    if last_text_idx is None:
        return None

    remaining   = range(last_text_idx + 1, len(paras))
    blank_after = [i for i in remaining if not _para_text(paras[i]).strip()]

    if not blank_after:
        return None

    has_dash = any(_is_dash_line(_para_text(paras[i])) for i in remaining)
    return blank_after[0], has_dash


# ── Text helpers ──────────────────────────────────────────────

def _extract_keyword(signature_path: str) -> str:
    """
    Ekstrak keyword dari nama file TTD.

    Handle konvensi penamaan yang umum:
        "Farino.png"               → "Farino"
        "Farino_Joshua.png"        → "Farino Joshua"
        "TTD_-_Farino_Joshua.png"  → "Farino Joshua"
        "TTD_Farino_Joshua.png"    → "Farino Joshua"
        "sign_Manager_IT.png"      → "Manager IT"
        "Division Head Divisi.png" → "Division Head Divisi"

    Steps:
        1. Strip ekstensi
        2. Strip prefix TTD/sign/tanda_tangan (case-insensitive)
        3. Ganti underscore → space
        4. Clean separator " - " → space
        5. Normalize whitespace
    """
    _PREFIXES = [
        "TTD_-_", "TTD_", "TTD-", "TTD ",
        "ttd_-_", "ttd_", "ttd-", "ttd ",
        "sign_", "sign-",
        "tanda_tangan_", "tanda-tangan-",
    ]

    basename = os.path.basename(signature_path)
    name, _  = os.path.splitext(basename)
    name     = name.strip()

    # Strip prefix (case-insensitive)
    lower = name.lower()
    for prefix in _PREFIXES:
        if lower.startswith(prefix.lower()):
            name  = name[len(prefix):]
            break

    # Underscore → space
    name = name.replace("_", " ")

    # " - " atau standalone "-" antara kata → space
    # (preserve dash di tengah kata: "Al-Farisi" tetap utuh)
    name = re.sub(r'\s*-\s*', ' ', name)

    return " ".join(name.split())


def _best_matching_line(keyword: str, cell_text: str) -> str:
    """
    Ekstrak baris paling relevan dari cell_text terhadap keyword.

    Cell bisa mengandung banyak baris — misalnya:
        "Developer\nFarino Joshua\nPT. Bank Negara Indonesia"

    Fungsi ini return baris yang mengandung keyword, bukan full cell text.
    Fallback ke baris pertama non-kosong jika tidak ada baris yang match.

    Contoh:
        keyword="Farino", cell="Farino Joshua"         → "Farino Joshua"
        keyword="Division Head", cell="Division Head\nDivisi IT\nPT. BNI"
                                                        → "Division Head"
        keyword="Manager", cell="Approval\nManager Keuangan\nPT. BNI"
                                                        → "Manager Keuangan"
    """
    lines = [l.strip() for l in cell_text.splitlines() if l.strip()]
    if not lines:
        return keyword

    kw_lower = keyword.lower()

    # Prioritas 1: baris yang mengandung keyword persis (case-insensitive)
    for line in lines:
        if kw_lower in line.lower():
            return line

    # Prioritas 2: baris yang mengandung kata terbanyak dari keyword
    kw_words = kw_lower.split()
    best_line  = lines[0]
    best_score = 0
    for line in lines:
        score = sum(1 for w in kw_words if w in line.lower())
        if score > best_score:
            best_score = score
            best_line  = line

    return best_line


def _is_dash_line(text: str) -> bool:
    stripped = text.strip().replace(" ", "")
    return len(stripped) >= DASH_LINE_MIN and all(c in "-_" for c in stripped)