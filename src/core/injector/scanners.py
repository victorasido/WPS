"""
services/injector/scanners.py
Logika deteksi slot whitespace di sekitar keyword pada halaman PDF.

Berisi:
- Konstanta geometri (padding, gap, dll)
- Low-level PDF line extractors (_extract_lines, _words, _ensure_min_height)
- Slot finders (_find_slot_above, _find_dash_above, _find_slot_below, _find_dash_below)
- Width expansion helper (_expand_width_if_narrow)

Modul ini tidak bergantung pada modul injector lain,
sehingga bisa dipakai secara independen.
"""

import re
import fitz

# ── Geometry Constants ────────────────────────────────────────

SIGNATURE_PADDING       = 6
MIN_SLOT_HEIGHT         = 30
MIN_GAP_WHITESPACE      = 20
DEBUG_MODE              = False
FALLBACK_ABOVE_DISTANCE = 80
FALLBACK_BELOW_DISTANCE = 60


# ── Low-level PDF Utilities ───────────────────────────────────

def extract_lines(page) -> list:
    """Ekstrak semua baris teks dari halaman PDF sebagai list dict."""
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


def words(text: str) -> list:
    """Tokenize teks: lowercase, hapus non-alphanumeric."""
    return re.sub(r"[^a-z0-9\s]", "", text.lower()).split()


def ensure_min_height(rect: fitz.Rect) -> fitz.Rect:
    """Pastikan rect memiliki tinggi minimal MIN_SLOT_HEIGHT."""
    if rect.height < MIN_SLOT_HEIGHT:
        rect = fitz.Rect(rect.x0, rect.y1 - MIN_SLOT_HEIGHT, rect.x1, rect.y1)
    return rect


# ── Width Expansion ───────────────────────────────────────────

def expand_width_if_narrow(col_x0: float, col_x1: float, min_width: float = 200.0) -> tuple[float, float]:
    """
    Symmetrically expand width from center if too narrow to ensure
    there's enough space to properly center the signature horizontally.
    """
    w = col_x1 - col_x0
    if w < min_width:
        cx     = (col_x0 + col_x1) / 2
        col_x0 = max(0, cx - (min_width / 2))
        col_x1 = col_x0 + min_width
    return col_x0, col_x1


def _find_horizontal_bounds(lines: list, page_width: float, y_top: float, y_bottom: float, keyword_x0: float, keyword_x1: float):
    """
    Horizontal Raycasting: meraba kekosongan (tembok kiri dan kanan)
    di dalam sebuah lorong/koridor spasial (y_top sampai y_bottom).
    Dibuat agar TTD bisa "nengah" secara elegan di ruang terbuka, 
    bukan memusat statis di atas kata kuncinya.
    """
    left_wall = 0.0          
    right_wall = page_width  

    for l in lines:
        if max(l["yt"], y_top) < min(l["yb"], y_bottom):
            if l["x1"] <= keyword_x0:
                left_wall = max(left_wall, l["x1"] + 15)
            elif l["x0"] >= keyword_x1:
                right_wall = min(right_wall, l["x0"] - 15)
                
    cx = (keyword_x0 + keyword_x1) / 2
    left_wall = max(left_wall, cx - 150)
    right_wall = min(right_wall, cx + 150)
    
    return left_wall, right_wall


# ── Slot Finders ──────────────────────────────────────────────

def find_slot_above(lines: list, name_idx: int, name_line: dict):
    """
    Cari blank space di atas nama dalam kolom yang sama.

    Menggunakan horizontal intersection logic agar lebih toleran
    terhadap teks yang beda alignment (misal nama rata kiri,
    title rata tengah).
    """
    col_x0 = name_line["x0"]
    col_x1 = name_line["x1"]

    # Toleransi horizon box (kiri & kanan ditambah 50pt)
    horizon_x0 = col_x0 - 50.0
    horizon_x1 = col_x1 + 50.0

    # L adalah satu kolom jika span horizontalnya overlap dengan horizon
    col_lines_above = sorted(
        [l for l in lines if (l["x1"] > horizon_x0 and l["x0"] < horizon_x1)
         and l["yt"] < name_line["yt"]],
        key=lambda l: l["yt"],
        reverse=True,  # terdekat (yt terbesar) duluan
    )

    if not col_lines_above:
        return None

    nearest = col_lines_above[0]
    gap     = name_line["yt"] - nearest["yb"]

    if gap < MIN_GAP_WHITESPACE:
        return None

    # Step 2: Raycast horizontal bounds dalam koridor ini
    # supaya dapat center poin yang lebih leluasa di ruang kosong
    col_x0, col_x1 = _find_horizontal_bounds(
        lines, 600.0, nearest["yb"], name_line["yt"], name_line["x0"], name_line["x1"]
    )

    # Capping ttd box height
    # Supaya tidak bablas kalau gap-nya sangat besar
    max_slot_height = 80.0
    top_y = nearest["yb"] + SIGNATURE_PADDING
    if (name_line["yt"] - SIGNATURE_PADDING - top_y) > max_slot_height:
        top_y = name_line["yt"] - SIGNATURE_PADDING - max_slot_height

    rect = fitz.Rect(
        col_x0,
        top_y,
        col_x1,
        name_line["yt"] - SIGNATURE_PADDING,
    )
    return ensure_min_height(rect)


def find_dash_above(lines: list, name_idx: int, name_line: dict):
    """Cari garis --- di atas nama dalam kolom yang sama."""
    col_x0 = name_line["x0"]
    col_x1 = name_line["x1"]
    horizon_x0 = col_x0 - 50.0
    horizon_x1 = col_x1 + 50.0

    for line in reversed(lines[:name_idx]):
        if not (line["x1"] > horizon_x0 and line["x0"] < horizon_x1):
            continue
        txt = line["text"].replace(" ", "")
        if len(txt) >= 4 and all(c in "-_" for c in txt):
            # Adopsi lebar dari garis ---- untuk perfect centering
            dash_x0 = line["x0"]
            dash_x1 = line["x1"]
            dash_x0, dash_x1 = expand_width_if_narrow(dash_x0, dash_x1)
            
            rect = fitz.Rect(
                dash_x0,
                max(line["yt"] - 80, line["yb"] + SIGNATURE_PADDING),
                dash_x1,
                line["yt"] - SIGNATURE_PADDING,
            )
            return ensure_min_height(rect)

    return None


def find_slot_below(lines: list, name_idx: int, name_line: dict):
    """
    Cari blank space di BAWAH nama dalam kolom yang sama.
    Digunakan sebagai fallback ketika slot di atas tidak ditemukan.
    """
    col_x0 = name_line["x0"]
    col_x1 = name_line["x1"]
    horizon_x0 = col_x0 - 50.0
    horizon_x1 = col_x1 + 50.0

    col_lines_below = sorted(
        [l for l in lines if (l["x1"] > horizon_x0 and l["x0"] < horizon_x1)
         and l["yt"] > name_line["yb"]],
        key=lambda l: l["yt"],
    )

    if not col_lines_below:
        return None

    nearest = col_lines_below[0]
    gap     = nearest["yt"] - name_line["yb"]

    if gap < MIN_GAP_WHITESPACE:
        return None

    # Step 2: Raycast horizontal bounds dalam koridor ini
    col_x0, col_x1 = _find_horizontal_bounds(
        lines, 600.0, name_line["yb"], nearest["yt"], name_line["x0"], name_line["x1"]
    )

    max_slot_height = 80.0
    bottom_y = nearest["yt"] - SIGNATURE_PADDING
    if (bottom_y - (name_line["yb"] + SIGNATURE_PADDING)) > max_slot_height:
        bottom_y = name_line["yb"] + SIGNATURE_PADDING + max_slot_height

    rect = fitz.Rect(
        col_x0,
        name_line["yb"] + SIGNATURE_PADDING,
        col_x1,
        bottom_y,
    )
    return ensure_min_height(rect)


def find_dash_below(lines: list, name_idx: int, name_line: dict):
    """Cari garis --- di BAWAH nama dalam kolom yang sama."""
    col_x0 = name_line["x0"]
    col_x1 = name_line["x1"]
    horizon_x0 = col_x0 - 50.0
    horizon_x1 = col_x1 + 50.0

    for line in lines[name_idx + 1:]:
        if not (line["x1"] > horizon_x0 and line["x0"] < horizon_x1):
            continue
        txt = line["text"].replace(" ", "")
        if len(txt) >= 4 and all(c in "-_" for c in txt):
            # Adopsi lebar dari garis ---- untuk perfect centering
            dash_x0 = line["x0"]
            dash_x1 = line["x1"]
            dash_x0, dash_x1 = expand_width_if_narrow(dash_x0, dash_x1)
            
            rect = fitz.Rect(
                dash_x0,
                line["yb"] + SIGNATURE_PADDING,
                dash_x1,
                min(line["yb"] + 80, line["yt"] + 80),
            )
            return ensure_min_height(rect)

    return None
