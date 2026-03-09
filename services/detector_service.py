# detector_service.py
# Deteksi zona TTD berdasarkan nama file TTD (jabatan lengkap)
# Struktur dokumen: merged cell, tiap slot TTD = blank* + garis + jabatan

import os
import re
from docx import Document
from docx.oxml.ns import qn
from core.config import CONFIDENCE_THRESHOLD, LAST_PAGES_SCAN

IGNORED_LINES = [
    "pt. bank negara indonesia (persero) tbk.",
    "pt. bank negara indonesia (persero)",
    "tbk.",
    "tbk",
]

DASH_LINE_MIN = 5  # minimal panjang karakter garis putus-putus


def detect_signature_zones(docx_path: str, signature_path: str,
                            confidence_threshold: float = None,
                            last_pages: int = None) -> list:
    """
    Scan DOCX dan return list zona TTD berdasarkan nama file TTD.

    Nama file = jabatan lengkap (tanpa PT. Bank...).
    Contoh: "Division Head Divisi Developer (RCL_WDL_ADV).png"
            → cari slot yang jabatannya cocok dalam cell

    Struktur slot TTD dalam cell:
        [blank paragraf x N]  ← ruang TTD, inject di blank terakhir
        [garis ---]
        [jabatan baris 1]     ← "Division Head"
        [jabatan baris 2]     ← "Divisi Developer (RCL/WDL/ADV)"
        [PT. Bank... ignored]

    Return: list of dict:
        - source          : "table"
        - paragraph_index : untuk sorting
        - table_location  : (t_idx, r_idx, c_idx, inject_p_idx)
        - matched_name    : jabatan yang cocok
        - confidence      : 1.0
        - context         : teks jabatan yang match
    """
    if confidence_threshold is None:
        confidence_threshold = CONFIDENCE_THRESHOLD
    if last_pages is None:
        last_pages = LAST_PAGES_SCAN

    target_text = _normalize_filename(signature_path)
    doc = Document(docx_path)
    zones = []
    seen_cell_ids: set = set()

    for t_idx, table in enumerate(doc.tables):
        for r_idx, row in enumerate(table.rows):
            for c_idx, cell in enumerate(row.cells):

                # Skip merged cell duplicate
                cell_id = id(cell)
                if cell_id in seen_cell_ids:
                    continue
                seen_cell_ids.add(cell_id)

                paras = cell.paragraphs

                # Parse cell jadi list of slot TTD
                slots = _parse_slots(paras)

                for slot in slots:
                    # Cocokkan jabatan slot dengan target nama file
                    slot_text = _join_jabatan(slot["jabatan_lines"])
                    if not _is_match(target_text, slot_text):
                        continue

                    inject_p_idx = slot["inject_p_idx"]

                    zones.append({
                        "source": "table",
                        "paragraph_index": 10000 + t_idx * 100 + r_idx * 10 + c_idx,
                        "table_location": (t_idx, r_idx, c_idx, inject_p_idx),
                        "matched_name": slot_text,
                        "confidence": 1.0,
                        "context": slot_text,
                    })

    zones.sort(key=lambda z: z["paragraph_index"])
    return zones


# ── Slot parser ──────────────────────────────────────────────

def _parse_slots(paras) -> list:
    """
    Parse paragraf dalam cell jadi list of slot TTD.

    Tiap slot:
        {
            "inject_p_idx" : index paragraf blank terakhir sebelum garis,
            "jabatan_lines": list of string jabatan (exclude PT. Bank...)
        }

    Strategi: scan dari atas, deteksi garis "---", lalu ambil
    blank sebelumnya sebagai ruang TTD dan teks setelahnya sebagai jabatan.
    """
    slots = []
    total = len(paras)

    i = 0
    while i < total:
        # Cari garis "---"
        if _is_dash_line(paras[i].text):
            dash_idx = i

            # Kumpulkan blank sebelum garis (ruang TTD)
            blank_indices = []
            j = dash_idx - 1
            while j >= 0 and paras[j].text.strip() == "":
                blank_indices.insert(0, j)
                j -= 1

            if not blank_indices:
                i += 1
                continue

            inject_p_idx = blank_indices[-1]  # blank terakhir sebelum garis

            # Kumpulkan jabatan setelah garis (sampai blank atau garis berikutnya)
            jabatan_lines = []
            k = dash_idx + 1
            while k < total:
                text = paras[k].text.strip()
                if not text or _is_dash_line(text):
                    break
                if not _is_ignored_line(text):
                    jabatan_lines.append(text)
                k += 1

            if jabatan_lines:
                slots.append({
                    "inject_p_idx": inject_p_idx,
                    "jabatan_lines": jabatan_lines,
                })

        i += 1

    return slots


# ── Text helpers ─────────────────────────────────────────────

def _normalize_filename(signature_path: str) -> str:
    """
    Ambil nama file, strip ekstensi, normalize karakter.
    "Division Head Divisi Developer (RCL_WDL_ADV).png"
    → "Division Head Divisi Developer (RCL/WDL/ADV)"
    """
    basename = os.path.basename(signature_path)
    name, _ = os.path.splitext(basename)
    # Ganti underscore di dalam kurung → slash
    name = re.sub(
        r'\(([^)]+)\)',
        lambda m: '(' + m.group(1).replace('_', '/') + ')',
        name
    )
    return name.strip()


def _join_jabatan(lines: list) -> str:
    """Gabungkan baris jabatan jadi satu string."""
    return " ".join(lines)


def _is_match(target: str, cell_text: str) -> bool:
    """Partial match, case sensitive, whitespace-normalized."""
    target_norm   = " ".join(target.split())
    celltext_norm = " ".join(cell_text.split())
    return target_norm in celltext_norm


def _is_dash_line(text: str) -> bool:
    """Deteksi garis putus-putus (--- atau ___)."""
    stripped = text.strip().replace(" ", "")
    return len(stripped) >= DASH_LINE_MIN and all(c in "-_" for c in stripped)


def _is_ignored_line(text: str) -> bool:
    """Cek apakah baris ini harus diabaikan (PT. Bank dst)."""
    return any(ignored in text.lower() for ignored in IGNORED_LINES)


# ── Page boundary helpers ────────────────────────────────────

def _find_last_pages_start(docx_path: str, paragraphs: list, last_n: int) -> int:
    result = _try_xml_page_breaks(paragraphs, last_n)
    if result is not None:
        return result
    result = _estimate_via_pymupdf(docx_path, len(paragraphs), last_n)
    if result is not None:
        return result
    return 0


def _try_xml_page_breaks(paragraphs: list, last_n: int):
    breaks_found = 0
    for idx in range(len(paragraphs) - 1, -1, -1):
        if _has_page_break(paragraphs[idx]):
            breaks_found += 1
            if breaks_found >= last_n:
                return idx + 1
    if breaks_found > 0:
        return 0
    return None


def _estimate_via_pymupdf(docx_path: str, total_paragraphs: int, last_n: int):
    try:
        import fitz
        doc = fitz.open(docx_path)
        total_pages = len(doc)
        doc.close()
        if total_pages <= last_n:
            return 0
        ratio = last_n / total_pages
        estimated = int(total_paragraphs * ratio * 1.15)
        return max(0, total_paragraphs - estimated)
    except Exception:
        return None


def _has_page_break(para) -> bool:
    for br in para._p.iter(qn("w:br")):
        if br.get(qn("w:type")) == "page":
            return True
    return False