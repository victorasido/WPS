"""
services/detector/docx_xml.py
Utility helpers untuk membaca dan menavigasi XML struktur .docx
(tbl → tr → tc → w:p → w:t).

Semua fungsi di sini bersifat "tukang gali" data murni — tidak ada
business logic deteksi di sini.
"""

from docx.oxml.ns import qn
from src.shared.text_utils import is_dash_line


# ── Cell / Paragraph Text Extraction ─────────────────────────

def tc_text(tc) -> str:
    """Ambil semua teks dari XML tc element, pisah per paragraf dengan newline."""
    paras = tc_paragraphs(tc)
    return "\n".join(para_text(p) for p in paras)


def tc_paragraphs(tc) -> list:
    """Return list of w:p elements dalam tc."""
    return tc.findall(qn("w:p"))


def para_text(p) -> str:
    """Ambil teks dari satu w:p element."""
    runs = p.findall(".//" + qn("w:t"))
    return "".join(r.text or "" for r in runs)


def is_tc_blank(tc) -> bool:
    """Cell kosong jika semua paragrafnya tidak punya teks."""
    return all(not para_text(p).strip() for p in tc_paragraphs(tc))


def has_dash_in_tc(tc) -> bool:
    """Return True jika ada baris garis dashes (---/___) dalam cell."""
    return any(is_dash_line(para_text(p)) for p in tc_paragraphs(tc))


def get_tc(xml_rows: list, r_idx: int, c_idx: int):
    """Ambil tc XML element di posisi (r_idx, c_idx). Return None jika out of range."""
    if r_idx < 0 or r_idx >= len(xml_rows):
        return None
    cells = xml_rows[r_idx].findall(qn("w:tc"))
    if c_idx < 0 or c_idx >= len(cells):
        return None
    return cells[c_idx]


# ── Slot Detection (blank space di sekitar keyword cell) ──────

def find_slot_xml(tc, xml_rows: list, r_idx: int, c_idx: int):
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
    paras = tc_paragraphs(tc)

    # 1. Blank para di atas dalam cell yang sama
    result = blank_above_in_paras(paras)
    if result is not None:
        inject_p_idx, has_dash = result
        return inject_p_idx, "above_same", has_dash

    # 2. Prev row, same column
    if r_idx > 0:
        prev_tc = get_tc(xml_rows, r_idx - 1, c_idx)
        if prev_tc is not None and is_tc_blank(prev_tc):
            _has_dash = has_dash_in_tc(tc)
            n_paras   = len(tc_paragraphs(prev_tc))
            return max(0, n_paras - 1), "above_prev_row", _has_dash

    # 3. Blank para di bawah dalam cell yang sama
    result = blank_below_in_paras(paras)
    if result is not None:
        inject_p_idx, has_dash = result
        return inject_p_idx, "below_same", has_dash

    # 4. Next row, same column
    if r_idx < len(xml_rows) - 1:
        next_tc = get_tc(xml_rows, r_idx + 1, c_idx)
        if next_tc is not None and is_tc_blank(next_tc):
            _has_dash = has_dash_in_tc(tc)
            return 0, "below_next_row", _has_dash

    # 5. Last Resort Fallback
    # Jika tidak ada blank space sama sekali dalam tabel super padat,
    # paksa injeksi di posisi atas teks pertama dalam sel.
    # Lebih baik TTD sedikit menimpa teks, daripada gagal 0 zones.
    return 0, "above_same", False


def blank_above_in_paras(paras: list):
    """
    Cari blank para terakhir sebelum teks pertama.
    Return (inject_p_idx, has_dash) atau None.
    """
    first_text_idx = next(
        (i for i, p in enumerate(paras) if para_text(p).strip()),
        None
    )
    if first_text_idx is None or first_text_idx == 0:
        return None

    has_dash = any(
        is_dash_line(para_text(paras[i]))
        for i in range(first_text_idx)
    )
    return first_text_idx - 1, has_dash


def blank_below_in_paras(paras: list):
    """
    Cari blank para pertama setelah teks terakhir.
    Return (inject_p_idx, has_dash) atau None.
    """
    last_text_idx = None
    for i in range(len(paras) - 1, -1, -1):
        if para_text(paras[i]).strip():
            last_text_idx = i
            break

    if last_text_idx is None:
        return None

    remaining   = range(last_text_idx + 1, len(paras))
    blank_after = [i for i in remaining if not para_text(paras[i]).strip()]

    if not blank_after:
        return None

    has_dash = any(is_dash_line(para_text(paras[i])) for i in remaining)
    return blank_after[0], has_dash
