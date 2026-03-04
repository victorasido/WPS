# detector_service.py
# Tanggung jawab: Scan DOCX, deteksi zona TTD di paragraf DAN tabel

from docx import Document
from docx.oxml.ns import qn
from core.config import CONFIDENCE_THRESHOLD, LAST_PAGES_SCAN

STRONG_KEYWORDS = [
    "tanda tangan", "signature", "ttd", "signed by", "ditandatangani",
]
# Catatan: "accepted by" dipindah ke MEDIUM karena sebagai row header
# ia tidak punya cukup ruang kosong → akan di-skip otomatis oleh table scanner
MEDIUM_KEYWORDS = [
    "mengetahui", "menyetujui", "hormat kami", "hormat saya", "mengesahkan",
    "division head",        # BNI DAC
    "accepted by", "accepted",
    "approver", "authorized by", "verified by",
]
WEAK_KEYWORDS = [
    "direktur", "manager", "kepala", "pimpinan", "jabatan", "materai", "stempel",
    "divisi", "division",   # BNI divisi name rows
    "head",
    "dept", "department",
]


def detect_signature_zones(docx_path: str, confidence_threshold: float = None,
                            last_pages: int = None) -> list:
    """
    Scan DOCX dan return list zona TTD yang terdeteksi.
    Mendeteksi di paragraf biasa DAN di dalam sel tabel.
    Hanya scan N halaman terakhir (default: LAST_PAGES_SCAN dari config).

    Return: list of dict dengan field:
        - source          : "paragraph" atau "table"
        - paragraph_index : index urut (untuk sorting)
        - table_location  : tuple (t_idx, r_idx, c_idx, p_idx) jika source="table", else None
        - keyword         : keyword pemicu deteksi
        - confidence      : score 0.0 - 1.0
        - context         : teks sekitar area TTD
    """
    if confidence_threshold is None:
        confidence_threshold = CONFIDENCE_THRESHOLD
    if last_pages is None:
        last_pages = LAST_PAGES_SCAN

    doc = Document(docx_path)
    zones = []

    # ── Tentukan batas scan (hanya N halaman terakhir) ───────
    paragraphs = doc.paragraphs
    total = len(paragraphs)
    scan_from = _find_last_pages_start(docx_path, paragraphs, last_pages)

    # ── Scan paragraf (bottom-first, dibatasi halaman terakhir) ─
    for idx in range(total - 1, scan_from - 1, -1):
        para = paragraphs[idx]
        text = para.text.lower().strip()
        keyword, confidence = _score_paragraph(para, text)

        if confidence >= confidence_threshold:
            zones.append({
                "source": "paragraph",
                "paragraph_index": idx,
                "table_location": None,
                "keyword": keyword,
                "confidence": round(confidence, 2),
                "context": para.text.strip(),
            })

    # ── Scan tabel ─────────────────────────────────────────────────────────
    # Tiap sel diproses sekali (merged cells share same object → skip duplicates).
    # Per sel: cari semua paragraf yang trigger, tentukan 1 titik inject terbaik.
    seen_cell_ids: set = set()

    for t_idx, table in enumerate(doc.tables):
        for r_idx, row in enumerate(table.rows):
            for c_idx, cell in enumerate(row.cells):

                # Skip sel yang sama (hasil merge)
                cell_id = id(cell)
                if cell_id in seen_cell_ids:
                    continue
                seen_cell_ids.add(cell_id)

                paras = cell.paragraphs

                # ── 1. Cari semua paragraf pemicu di sel ini ──────────────
                triggers = []   # list of (p_idx, keyword, confidence)
                for p_idx, para in enumerate(paras):
                    text = para.text.lower().strip()
                    keyword, confidence = _score_paragraph(para, text)
                    if confidence >= confidence_threshold:
                        triggers.append((p_idx, keyword, confidence))

                if not triggers:
                    continue

                # ── 2. Hitung & cari paragraf kosong SEBELUM trigger pertama ─
                #    Zona TTD yang valid punya MINIMAL 2 blank paragraph (ruang
                #    untuk tanda tangan). Header row ("Accepted by:") biasanya
                #    hanya punya ≤1 blank padding → langsung skip.
                first_trigger_idx = triggers[0][0]

                blank_before = [
                    p_idx for p_idx in range(first_trigger_idx)
                    if _is_blank_or_short(paras[p_idx].text.strip())
                ]

                # Syarat: minimal 2 paragraf kosong sebelum trigger
                if len(blank_before) < 2:
                    continue  # header row / bukan slot TTD → skip

                # Titik inject = blank terakhir sebelum trigger (tepat di atas garis)
                inject_p_idx = blank_before[-1]

                # Validasi: pastikan target inject benar-benar kosong
                if paras[inject_p_idx].text.strip() != "":
                    continue

                # ── 3. Ambil confidence & keyword tertinggi dari semua trigger ─
                best = max(triggers, key=lambda x: x[2])
                best_keyword, best_confidence = best[1], best[2]
                trigger_ctx = paras[first_trigger_idx].text.strip()

                zones.append({
                    "source": "table",
                    "paragraph_index": 10000 + t_idx * 100 + r_idx * 10 + c_idx,
                    "table_location": (t_idx, r_idx, c_idx, inject_p_idx),
                    "keyword": best_keyword,
                    "confidence": round(best_confidence, 2),
                    "context": trigger_ctx or "(ruang TTD)",
                })

    # Urutkan berdasarkan posisi
    zones.sort(key=lambda z: z["paragraph_index"])
    return zones


# ── Page boundary helpers ────────────────────────────────────

def _find_last_pages_start(docx_path: str, paragraphs: list, last_n: int) -> int:
    """
    Cari index paragraf awal dari N halaman terakhir.
    Strategi 1: deteksi page break eksplisit di XML (paling akurat).
    Strategi 2: estimasi proporsional via PyMuPDF (fallback).
    Strategi 3: scan seluruh dokumen (fallback akhir).
    """
    # Strategi 1: XML page breaks
    result = _try_xml_page_breaks(paragraphs, last_n)
    if result is not None:
        return result

    # Strategi 2: PyMuPDF proportional estimate
    result = _estimate_via_pymupdf(docx_path, len(paragraphs), last_n)
    if result is not None:
        return result

    # Strategi 3: scan penuh
    return 0


def _try_xml_page_breaks(paragraphs: list, last_n: int):
    """
    Cari page break eksplisit (<w:br w:type="page"/>) dari bawah ke atas.
    Return index paragraf setelah break ke-N dari bawah, atau None jika kurang.
    """
    breaks_found = 0
    for idx in range(len(paragraphs) - 1, -1, -1):
        if _has_page_break(paragraphs[idx]):
            breaks_found += 1
            if breaks_found >= last_n:
                return idx + 1  # scan dari paragraf setelah break ini
    # Kurang dari last_n page break ditemukan
    if breaks_found > 0:
        return 0  # lebih sedikit halaman dari last_n → scan semua
    return None   # tidak ada page break sama sekali → coba fallback


def _estimate_via_pymupdf(docx_path: str, total_paragraphs: int, last_n: int):
    """
    Gunakan PyMuPDF untuk tahu total halaman, lalu estimasi proporsi paragraf
    yang masuk ke dalam last_n halaman. Return scan_from index atau None.
    """
    try:
        import fitz  # pymupdf
        doc = fitz.open(docx_path)
        total_pages = len(doc)
        doc.close()

        if total_pages <= last_n:
            return 0  # dokumen <= last_n halaman → scan semua

        # Estimasi: last_n/total_pages dari paragraf terakhir + buffer 15%
        ratio = last_n / total_pages
        estimated = int(total_paragraphs * ratio * 1.15)
        scan_from = max(0, total_paragraphs - estimated)
        return scan_from
    except Exception:
        return None


def _has_page_break(para) -> bool:
    """Cek apakah paragraf mengandung explicit page break di XML."""
    for br in para._p.iter(qn("w:br")):
        if br.get(qn("w:type")) == "page":
            return True
    return False


def _score_paragraph(para, text: str) -> tuple:
    """Hitung confidence score paragraf. Return: (keyword, score)"""
    keyword_found = None
    score = 0.0

    for kw in STRONG_KEYWORDS:
        if kw in text:
            keyword_found = kw
            score += 0.7
            break

    if not keyword_found:
        for kw in MEDIUM_KEYWORDS:
            if kw in text:
                keyword_found = kw
                score += 0.5
                break

    if not keyword_found:
        for kw in WEAK_KEYWORDS:
            if kw in text:
                keyword_found = kw
                score += 0.3
                break

    if _has_underline(para):
        score += 0.2
    if _is_blank_or_short(text):
        score += 0.15
    if _is_dash_line(text):
        score += 0.4  # garis putus-putus = indikator kuat ruang TTD
        if not keyword_found:
            keyword_found = "(garis TTD)"

    return keyword_found, min(score, 1.0)


def _has_underline(para) -> bool:
    for run in para.runs:
        if run.underline:
            return True
    return False


def _is_blank_or_short(text: str) -> bool:
    return len(text) == 0 or len(text) <= 5


def _is_dash_line(text: str) -> bool:
    """Deteksi baris berisi garis putus-putus (----/____) sebagai ruang TTD."""
    stripped = text.replace(" ", "")
    if len(stripped) < 4:
        return False
    return len(stripped) >= 4 and all(c in "-_" for c in stripped)