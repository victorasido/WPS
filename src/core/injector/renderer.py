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
from opentelemetry import trace
from src.infra.telemetry.telemetry_setup import tracer

logger = logging.getLogger(__name__)

# ── Absolute size constraints ─────────────────────────────────
# Mencegah tanda tangan raksasa di slot yang sangat lebar.
MAX_ABS_WIDTH  = 160.0  # pt
MAX_ABS_HEIGHT = 80.0   # pt


@tracer.start_as_current_span("place_image_with_constraints")
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
    span = trace.get_current_span()
    span.set_attribute("geometry.zone_width",  rect.width)
    span.set_attribute("geometry.zone_height", rect.height)

    processor = SignatureImageProcessor()
    sig_bytes, iw, ih = processor.process(sig_bytes)

    zone_w = rect.width
    zone_h = rect.height

    target_w  = min(zone_w * 0.85, MAX_ABS_WIDTH)
    target_h  = min(zone_h * 0.85, MAX_ABS_HEIGHT)
    max_scale = min(target_w / iw, target_h / ih, 2.0)
    min_scale = 0.4
    step      = 0.1

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
