"""
services/injector/renderer.py
Eksekusi fisik penyisipan gambar TTD ke halaman PDF.

Tanggung jawab tunggal (SRP):
- Terima page, rect, dan bytes gambar
- Proses gambar via SignatureImageProcessor (crop, bg removal)
- Hitung skala proporsional dengan absolute size constraints
- Cob iterasi scale → cek overlap → insert
- Jika semua scale overlap, insert di scale terkecil (last resort)

Tidak ada logika "mencari koordinat" di sini —
itu tanggung jawab legacy_scorer.py dan pdf_placer.
"""

import logging
import fitz
from src.shared.image_utils import SignatureImageProcessor
from src.shared.pdf_utils import rect_overlaps_text

logger = logging.getLogger(__name__)

# ── Absolute size constraints ─────────────────────────────────
# Tetap sebagai global cap agar TTD tidak melampaui ukuran ini.
MAX_ABS_WIDTH  = 150.0  # pt (~5.3cm)
MAX_ABS_HEIGHT = 75.0   # pt (~2.6cm)


def _zone_scale_factor(zone_w: float, zone_h: float) -> float:
    """
    Zone-Aware Adaptive Scale — Opsi C.

    Zona sempit (form kolom kecil kayak absensi) → scale kecil agar TTD proporsional.
    Zona lebar (dokumen approval normal) → scale besar untuk visual yang baik.

    Threshold zone_w (lebar zona, pt):
        < 130pt  →  narrow  (absensi, form 3-kolom)       → factor 0.60
        130–199  →  medium  (approval 2-kolom)             → factor 0.72
        ≥ 200pt  →  wide    (1-kolom, dokumen TSD/memo)   → factor 0.82

    Threshold zone_h (tinggi zona, pt):
        < 60pt   →  compact (baris tunggal pendek)        → factor 0.55
        60–99    →  normal                                → factor 0.70
        ≥ 100pt  →  tall                                  → factor 0.82

    Final = min(faktor_lebar, faktor_tinggi) agar fit dalam 2D zone.
    """
    # Width axis
    if zone_w < 130:
        fw = 0.60
    elif zone_w < 200:
        fw = 0.72
    else:
        fw = 0.82

    # Height axis
    if zone_h < 60:
        fh = 0.55
    elif zone_h < 100:
        fh = 0.70
    else:
        fh = 0.82

    return min(fw, fh)


def insert_image(page, rect: fitz.Rect, sig_bytes: bytes):
    """
    Sisipkan TTD ke dalam rect dengan geometric constraints.

    Pipeline:
    1. Proses gambar: hapus background + auto-crop (via SignatureImageProcessor)
    2. Hitung skala: fit ke 85% zona, cap max 160×80pt, cap upscale 2×
    3. Iterasi scale turun sampai tidak overlap teks
    4. Bottom-aligned, center horizontal
    5. Fallback: insert di scale terkecil meski overlap (agar user tetap dapat PDF)
    """
    processor = SignatureImageProcessor()
    sig_bytes, iw, ih = processor.process(sig_bytes)

    zone_w = rect.width
    zone_h = rect.height

    # Zone-Aware Adaptive Scale: faktor berbeda untuk zona sempit vs lebar
    scale_factor = _zone_scale_factor(zone_w, zone_h)
    target_w  = min(zone_w * scale_factor, MAX_ABS_WIDTH)
    target_h  = min(zone_h * scale_factor, MAX_ABS_HEIGHT)
    max_scale = min(target_w / iw, target_h / ih, 2.0)
    min_scale = 0.3
    step      = 0.05  # step lebih halus untuk fine-tune di zona kecil

    logger.debug(
        f"[INJ]   zone={zone_w:.0f}x{zone_h:.0f}pt "
        f"scale_factor={scale_factor:.2f} "
        f"target={target_w:.0f}x{target_h:.0f}pt"
    )

    inserted     = False
    tried_scales = []

    s = max_scale
    while s >= min_scale:
        fw = iw * s
        fh = ih * s

        # Center horizontal, bottom-aligned
        cx = rect.x0 + (zone_w - fw) / 2
        cy = max(rect.y0, rect.y1 - fh)

        img_rect = fitz.Rect(cx, cy, cx + fw, cy + fh)
        tried_scales.append(s)

        if not rect_overlaps_text(page, img_rect):
            logger.debug(
                f"[INJ]   zone={zone_w:.0f}×{zone_h:.0f}pt → "
                f"img={fw:.0f}×{fh:.0f}pt scale={s:.2f}"
            )
            page.insert_image(img_rect, stream=sig_bytes)
            inserted = True
            break

        s -= step

    if not inserted:
        # Last resort: insert at smallest attempted scale even if overlap
        s  = max(min_scale, min(max_scale, s + step))
        fw = iw * s
        fh = ih * s
        cx = rect.x0 + (zone_w - fw) / 2
        cy = max(rect.y0, rect.y1 - fh)
        logger.debug(
            f"[INJ]   fallback insert (overlap) scale={s:.2f}, tried={tried_scales}"
        )
        page.insert_image(fitz.Rect(cx, cy, cx + fw, cy + fh), stream=sig_bytes)
