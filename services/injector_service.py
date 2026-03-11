# injector_service.py
# Approach: inject TTD langsung ke PDF via PyMuPDF
# Strategy: pakai get_text("dict") untuk dapat posisi y tiap baris secara akurat

import io
import re
import fitz
from PIL import Image
from core.config import ALLOWED_SIGNATURE_FORMATS

SIGNATURE_PADDING = 4


def inject_signature(pdf_bytes: bytes, signature_path: str,
                     signature_zones: list) -> bytes:
    _validate_signature_format(signature_path)
    sig_bytes = _prepare_signature(signature_path)

    doc = fitz.open(stream=pdf_bytes, filetype="pdf")

    for zone in signature_zones:
        matched_name = zone.get("matched_name", "")
        if not matched_name:
            continue

        result = _find_signature_rect(doc, matched_name)
        if result is None:
            print(f"[INJ] ⚠ Tidak ditemukan di PDF: {matched_name!r}")
            continue

        page, sig_rect = result
        print(f"[INJ] ✓ {matched_name!r} → page={page.number+1} "
              f"rect=({sig_rect.x0:.0f},{sig_rect.y0:.0f},"
              f"{sig_rect.x1:.0f},{sig_rect.y1:.0f})")

        _insert_image(page, sig_rect, sig_bytes)

    output = io.BytesIO()
    doc.save(output)
    doc.close()
    output.seek(0)
    return output.read()


def _find_signature_rect(doc: fitz.Document, matched_name: str):
    """
    Cari zona TTD di PDF menggunakan get_text("dict") untuk posisi y akurat.

    Strategy:
    1. Filter halaman yang mengandung jabatan via blocks (cepat)
    2. Di halaman itu, ambil semua baris dengan posisi y akurat via "dict"
    3. Filter baris dalam kolom x yang sama dengan block jabatan
    4. Cari baris jabatan → cari garis --- di atasnya → hitung zona kosong
    """
    target = _normalize(matched_name)

    for page in doc:
        # Step 1: cari halaman yang relevan
        blocks_raw = page.get_text("blocks")
        found_block = None
        for block in blocks_raw:
            x0, y0, x1, y1, text, *_ = block
            if target in _normalize(text):
                found_block = (x0, y0, x1, y1)
                break
        if not found_block:
            continue

        bx0, by0, bx1, by1 = found_block

        # Step 2: ambil semua baris dengan posisi y akurat
        page_dict = page.get_text("dict")
        all_lines = []
        for blk in page_dict["blocks"]:
            if blk.get("type") != 0:
                continue
            for line in blk.get("lines", []):
                line_text = " ".join(s["text"] for s in line["spans"]).strip()
                if not line_text:
                    continue
                bbox = line["bbox"]
                all_lines.append({
                    "yt": bbox[1], "yb": bbox[3],
                    "x0": bbox[0], "x1": bbox[2],
                    "text": line_text
                })

        # Step 3: filter baris dalam kolom x block jabatan
        col_lines = [
            l for l in all_lines
            if l["x0"] >= bx0 - 15 and l["x1"] <= bx1 + 15
        ]
        col_lines.sort(key=lambda l: l["yt"])

        # Step 4: cari jabatan dan garis --- di atasnya
        jabatan_parts = _split_jabatan(matched_name)
        first_part    = _normalize(jabatan_parts[0])

        dash_y  = None
        sig_top = by0

        for i, line in enumerate(col_lines):
            if first_part not in _normalize(line["text"]):
                continue

            # Cari garis --- di atas baris jabatan ini
            for j in range(i - 1, -1, -1):
                prev = col_lines[j]["text"].replace(" ", "")
                if len(prev) >= 5 and all(c in "-_" for c in prev):
                    dash_y = col_lines[j]["yt"]
                    # sig_top = baris terakhir di atas garis, atau by0
                    sig_top = col_lines[j - 1]["yb"] + SIGNATURE_PADDING if j > 0 else by0
                    break
            break

        if dash_y is None:
            print(f"[INJ] ⚠ Garis tidak ditemukan di atas: {matched_name!r}")
            continue

        sig_rect = fitz.Rect(
            bx0 + SIGNATURE_PADDING,
            sig_top,
            bx1 - SIGNATURE_PADDING,
            dash_y - SIGNATURE_PADDING
        )

        if sig_rect.height < 10:
            print(f"[INJ] ⚠ Zona terlalu kecil: {sig_rect.height:.0f}pt")
            continue

        return page, sig_rect

    return None


def _insert_image(page: fitz.Page, rect: fitz.Rect, sig_bytes: bytes):
    """Insert gambar ke rect, resize proporsional, bottom-aligned, center horizontal."""
    img    = Image.open(io.BytesIO(sig_bytes))
    iw, ih = img.size
    zone_w = rect.width
    zone_h = rect.height

    # Fit ke 75% lebar dan 85% tinggi zone
    max_w  = zone_w * 0.75
    max_h  = zone_h * 0.85
    scale  = min(max_w / iw, max_h / ih, 1.0)
    fw, fh = iw * scale, ih * scale

    # Center horizontal dalam slot
    cx = rect.x0 + (zone_w - fw) / 2
    # Bottom-aligned: nempel ke garis ---
    cy = rect.y1 - fh

    img_rect = fitz.Rect(cx, cy, cx + fw, cy + fh)
    print(f"[INJ]   zone={zone_w:.0f}x{zone_h:.0f}pt → img={fw:.0f}x{fh:.0f}pt (centered)")

    page.insert_image(img_rect, stream=sig_bytes)


def _normalize(text: str) -> str:
    return " ".join(text.lower().split())


def _split_jabatan(matched_name: str) -> list:
    match = re.search(r'(?<!^)\s+(Divisi\s)', matched_name)
    if match:
        idx = match.start()
        return [matched_name[:idx].strip(), matched_name[idx:].strip()]
    return [matched_name]


def _validate_signature_format(signature_path: str):
    ext = signature_path.rsplit(".", 1)[-1].lower()
    if ext not in ALLOWED_SIGNATURE_FORMATS:
        raise ValueError(f"Format tidak didukung: .{ext}")


def _prepare_signature(signature_path: str) -> bytes:
    ext = signature_path.rsplit(".", 1)[-1].lower()
    if ext == "svg":
        import cairosvg
        return cairosvg.svg2png(url=signature_path)
    elif ext in ["jpg", "jpeg"]:
        img = Image.open(signature_path).convert("RGBA")
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        buf.seek(0)
        return buf.read()
    else:
        with open(signature_path, "rb") as f:
            return f.read()


def _clear_paragraph(para):
    from docx.oxml.ns import qn
    p = para._p
    for r in p.findall(qn("w:r")):
        p.remove(r)
    for hl in p.findall(qn("w:hyperlink")):
        p.remove(hl)