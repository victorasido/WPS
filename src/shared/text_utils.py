import os
import re
from src.infra.config import DASH_LINE_MIN

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

    # Clean separator " - " atau standalone "-" antara kata → space
    # (preserve dash di tengah kata: "Al-Farisi" tetap utuh)
    name = re.sub(r'\s*-\s*', ' ', name)

    # Clean characters like (), [], etc that often appear in filenames
    name = re.sub(r'[()\[\]]', ' ', name)

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
    kw_words = kw_lower.split()

    def line_score(line: str) -> int:
        ll = line.lower()
        return sum(1 for w in kw_words if w in ll)

    def is_separator(line: str) -> bool:
        """Baris pemisah antar slot (garis --- atau baris kosong)."""
        stripped = line.strip().replace(" ", "")
        return len(stripped) >= 3 and all(c in "-_" for c in stripped)

    # Step 1: Temukan baris dengan skor tertinggi sebagai "anchor"
    best_idx   = max(range(len(lines)), key=lambda i: line_score(lines[i]))
    best_score = line_score(lines[best_idx])

    # Jika anchor tidak punya satupun kata keyword, fallback ke baris pertama
    if best_score == 0:
        return lines[0]

    # Step 2: Expand ke atas dari anchor (selama ada irisan kata & bukan separator)
    start = best_idx
    while start > 0:
        candidate = lines[start - 1]
        if is_separator(candidate) or line_score(candidate) == 0:
            break
        start -= 1

    # Step 3: Expand ke bawah dari anchor (selama ada irisan kata & bukan separator)
    end = best_idx
    while end < len(lines) - 1:
        candidate = lines[end + 1]
        if is_separator(candidate) or line_score(candidate) == 0:
            break
        end += 1

    # Gabungkan blok kontigu yang ditemukan
    block = lines[start : end + 1]
    return " \n".join(block) if len(block) > 1 else block[0]


def is_dash_line(text: str) -> bool:
    stripped = text.strip().replace(" ", "")
    return len(stripped) >= DASH_LINE_MIN and all(c in "-_" for c in stripped)


def classify_label(text: str) -> str:
    """
    Klasifikasi semantic dari text: apakah nama, role, atau unknown.
    
    Heuristic:
    - ROLE: mengandung keyword seperti manager, head, supervisor, etc.
    - NAME: 2-4 kata dengan huruf besar
    - UNKNOWN: tidak clear
    """
    text_lower = text.lower()
    
    ROLE_HINTS = [
        "manager", "head", "supervisor", "lead",
        "director", "approval", "approver", "chief",
        "officer", "coordinator", "admin", "staff",
        "division", "department", "unit", "section",
    ]
    
    # Check role hints
    if any(hint in text_lower for hint in ROLE_HINTS):
        return "role"
    
    # Check if looks like name: 2-4 words, mostly capitalized
    words = text.split()
    if 2 <= len(words) <= 4:
        # Count capitalized words
        capitalized = sum(1 for w in words if w and w[0].isupper())
        if capitalized >= len(words) - 1:  # mostly capitalized
            return "name"
    
    return "unknown"
