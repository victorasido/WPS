# injector_service.py
# Tanggung jawab: Inject TTD ke zona terdeteksi di DOCX (paragraf & tabel)

import io
import os
from docx import Document
from docx.shared import Inches
from docx.oxml.ns import qn
from PIL import Image
from core.config import ALLOWED_SIGNATURE_FORMATS


def inject_signature(docx_path: str, signature_path: str,
                     signature_zones: list, width_inches: float = 1.5) -> bytes:
    """
    Inject TTD ke paragraf/sel tabel yang terdeteksi sebagai zona TTD.

    Args:
        docx_path       : path file DOCX asli
        signature_path  : path file TTD (svg/png/jpg)
        signature_zones : hasil dari detect_signature_zones()
        width_inches    : lebar gambar TTD (default 1.5)

    Return:
        bytes — DOCX yang sudah ada TTD-nya
    """
    _validate_signature_format(signature_path)
    signature_bytes = _prepare_signature(signature_path)

    doc = Document(docx_path)

    for zone in signature_zones:
        if zone["source"] == "paragraph":
            para = doc.paragraphs[zone["paragraph_index"]]
        else:  # table
            t_idx, r_idx, c_idx, p_idx = zone["table_location"]
            para = doc.tables[t_idx].rows[r_idx].cells[c_idx].paragraphs[p_idx]

        _clear_paragraph(para)
        run = para.add_run()
        run.add_picture(io.BytesIO(signature_bytes), width=Inches(width_inches))

    output = io.BytesIO()
    doc.save(output)
    output.seek(0)
    return output.read()


def _validate_signature_format(signature_path: str):
    ext = signature_path.rsplit(".", 1)[-1].lower()
    if ext not in ALLOWED_SIGNATURE_FORMATS:
        raise ValueError(
            f"Format tidak didukung: .{ext}. Gunakan: {ALLOWED_SIGNATURE_FORMATS}"
        )


def _prepare_signature(signature_path: str) -> bytes:
    """Normalise semua format TTD ke PNG bytes."""
    ext = signature_path.rsplit(".", 1)[-1].lower()
    if ext == "svg":
        return _svg_to_png(signature_path)
    elif ext in ["jpg", "jpeg"]:
        return _jpg_to_png(signature_path)
    else:
        with open(signature_path, "rb") as f:
            return f.read()


def _svg_to_png(svg_path: str) -> bytes:
    import cairosvg
    return cairosvg.svg2png(url=svg_path)


def _jpg_to_png(jpg_path: str) -> bytes:
    img = Image.open(jpg_path).convert("RGBA")
    output = io.BytesIO()
    img.save(output, format="PNG")
    output.seek(0)
    return output.read()


def _clear_paragraph(para):
    """
    Hapus semua runs (teks & gambar) dari paragraf sebelum insert TTD.
    Menggunakan XML langsung untuk memastikan embedded images juga terhapus.
    """
    p_elem = para._p
    # Hapus semua elemen <w:r> (yang menampung teks maupun gambar)
    for r_elem in p_elem.findall(qn("w:r")):
        p_elem.remove(r_elem)
    # Hapus hyperlinks yang mungkin berisi runs
    for hl_elem in p_elem.findall(qn("w:hyperlink")):
        p_elem.remove(hl_elem)