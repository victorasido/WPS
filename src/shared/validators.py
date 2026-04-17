import logging

logger = logging.getLogger(__name__)

MAX_FILE_BYTES = 20 * 1024 * 1024  # 20 MB

def validate_document_file(doc_name: str, file_size: int = None) -> tuple[bool, str]:
    """
    Validate document filename and size.
    
    Returns:
        (is_valid, error_message)
    """
    filename = (doc_name or "").lower()
    is_docx  = filename.endswith(".docx")
    is_pdf   = filename.endswith(".pdf")

    if not (is_docx or is_pdf):
        return False, (
            "❌ Format tidak didukung.\n\n"
            "Kirim file *.docx* atau *.pdf* ya. "
            "Format seperti `.doc`, `.xls`, dll belum didukung."
        )

    if file_size and file_size > MAX_FILE_BYTES:
        return False, (
            "❌ File terlalu besar (maks 20MB).\n"
            "Untuk PDF besar, coba compress dulu ya."
        )

    return True, ""


def validate_signature_file(doc_name: str, mime_type: str = None) -> tuple[bool, str]:
    """
    Validate signature image filename and mime type.
    """
    if mime_type and not mime_type.startswith("image/"):
        return False, "⚠️ File ini bukan gambar. Kirim gambar tanda tangan ya (PNG, JPG, atau SVG)."

    ext = (doc_name or "").rsplit(".", 1)[-1].lower()
    if ext not in ["png", "jpg", "jpeg", "svg"]:
        return False, "❌ Format tanda tangan harus *PNG, JPG, atau SVG*."

    return True, ""


def validate_keyword(keyword: str) -> tuple[bool, str]:
    """Validate search keyword length."""
    k = (keyword or "").strip()
    if not k or len(k) < 3:
        return False, "⚠️ Keyword terlalu pendek. Minimal 3 karakter.\nContoh: `Kepala Divisi IT`"
    return True, ""
