# injector_service.py
# Base: inject simpel, tambah resize agar tidak overflow slot TTD

import io
from docx import Document
from docx.shared import Inches, Emu
from docx.oxml.ns import qn
from PIL import Image
from core.config import ALLOWED_SIGNATURE_FORMATS

EMU_PER_INCH = 914400
EMU_PER_TWIP = 914400 / 1440
DPI          = 96
DEFAULT_LINE_EMU = int(240 * EMU_PER_TWIP)  # ~152,400 EMU = 1 baris normal


def inject_signature(docx_path: str, signature_path: str,
                     signature_zones: list, width_inches: float = 1.5) -> bytes:
    _validate_signature_format(signature_path)
    signature_bytes = _prepare_signature(signature_path)
    sig_img = Image.open(io.BytesIO(signature_bytes))
    sig_w_px, sig_h_px = sig_img.size

    doc = Document(docx_path)

    for zone in signature_zones:
        if zone["source"] == "paragraph":
            para      = doc.paragraphs[zone["paragraph_index"]]
            container = None
        else:
            t_idx, r_idx, c_idx, p_idx = zone["table_location"]
            cell      = doc.tables[t_idx].rows[r_idx].cells[c_idx]
            para      = cell.paragraphs[p_idx]
            container = cell

        # Hitung max width dari cell, fallback ke width_inches
        max_w_emu = _get_cell_width_emu(container, width_inches)

        # Hitung max height dari jumlah blank paragraphs di slot ini
        if container is not None:
            blank_indices = _get_blank_indices(cell.paragraphs, p_idx)
            max_h_emu = sum(_get_para_height_emu(cell.paragraphs[i])
                            for i in blank_indices)
        else:
            max_h_emu = int(width_inches * EMU_PER_INCH)  # fallback

        # Resize proporsional agar fit di slot
        final_w, final_h = _calc_fit_size(
            sig_w_px, sig_h_px, max_w_emu, max_h_emu
        )

        # Inject — sama persis dengan base version, cuma width/height dynamic
        _clear_paragraph(para)
        run = para.add_run()
        run.add_picture(io.BytesIO(signature_bytes),
                        width=Emu(final_w), height=Emu(final_h))

    output = io.BytesIO()
    doc.save(output)
    output.seek(0)
    return output.read()


# ── Helpers ──────────────────────────────────────────────────

def _get_blank_indices(paras, inject_p_idx: int) -> list:
    indices = []
    j = inject_p_idx
    while j >= 0 and paras[j].text.strip() == "":
        indices.insert(0, j)
        j -= 1
    return indices


def _get_para_height_emu(para) -> int:
    try:
        pPr = para._p.find(qn("w:pPr"))
        if pPr is not None:
            spacing = pPr.find(qn("w:spacing"))
            if spacing is not None:
                line = spacing.get(qn("w:line"))
                if line:
                    return int(int(line) * EMU_PER_TWIP)
    except Exception:
        pass
    return DEFAULT_LINE_EMU


def _get_cell_width_emu(container, fallback_inches: float) -> int:
    if container is not None:
        try:
            tcPr = container._tc.find(qn("w:tcPr"))
            if tcPr is not None:
                tcW = tcPr.find(qn("w:tcW"))
                if tcW is not None:
                    w_val  = tcW.get(qn("w:w"))
                    w_type = tcW.get(qn("w:type"), "dxa")
                    if w_val and w_type == "dxa":
                        return int(int(w_val) * EMU_PER_TWIP)
        except Exception:
            pass
    return int(fallback_inches * EMU_PER_INCH)


def _calc_fit_size(img_w_px: int, img_h_px: int,
                   max_w_emu: int, max_h_emu: int) -> tuple:
    img_w_emu = int(img_w_px / DPI * EMU_PER_INCH)
    img_h_emu = int(img_h_px / DPI * EMU_PER_INCH)

    # Scale by width
    scale = min(max_w_emu / img_w_emu, 1.0)
    w = int(img_w_emu * scale)
    h = int(img_h_emu * scale)

    # Scale by height jika masih overflow
    if max_h_emu > 0 and h > max_h_emu:
        scale2 = max_h_emu / h
        w = int(w * scale2)
        h = int(h * scale2)

    MIN_EMU = int(0.25 * EMU_PER_INCH)
    return max(w, MIN_EMU), max(h, MIN_EMU)


# ── Format helpers ───────────────────────────────────────────

def _validate_signature_format(signature_path: str):
    ext = signature_path.rsplit(".", 1)[-1].lower()
    if ext not in ALLOWED_SIGNATURE_FORMATS:
        raise ValueError(
            f"Format tidak didukung: .{ext}. Gunakan: {ALLOWED_SIGNATURE_FORMATS}"
        )


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
    p_elem = para._p
    for r_elem in p_elem.findall(qn("w:r")):
        p_elem.remove(r_elem)
    for hl_elem in p_elem.findall(qn("w:hyperlink")):
        p_elem.remove(hl_elem)