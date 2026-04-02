import os
import re
from core.config import DASH_LINE_MIN

def extract_keyword(signature_path: str) -> str:
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


def best_matching_line(keyword: str, cell_text: str) -> str:
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


def is_dash_line(text: str) -> bool:
    stripped = text.strip().replace(" ", "")
    return len(stripped) >= DASH_LINE_MIN and all(c in "-_" for c in stripped)
