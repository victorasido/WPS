# converter_service.py
# Tanggung jawab: Convert DOCX bytes → PDF bytes
# Coba LibreOffice headless dulu, fallback ke docx2pdf jika gagal

import io
import os
import subprocess
import tempfile
from core.config import LIBREOFFICE_PATH


def convert_to_pdf(signed_docx_bytes: bytes) -> bytes:
    """
    Convert DOCX bytes ke PDF bytes.
    Prioritas: LibreOffice headless → fallback docx2pdf
    """
    try:
        return _convert_with_libreoffice(signed_docx_bytes)
    except Exception as lo_err:
        try:
            return _convert_with_docx2pdf(signed_docx_bytes)
        except ImportError:
            raise RuntimeError(
                f"LibreOffice gagal: {lo_err}\n\n"
                "Fallback docx2pdf tidak tersedia.\n"
                "Install dengan: pip install docx2pdf"
            )
        except Exception as dp_err:
            raise RuntimeError(
                f"Semua converter gagal.\n"
                f"LibreOffice: {lo_err}\n"
                f"docx2pdf: {dp_err}"
            )


def _convert_with_libreoffice(signed_docx_bytes: bytes) -> bytes:
    if not os.path.exists(LIBREOFFICE_PATH):
        raise FileNotFoundError(f"LibreOffice tidak ditemukan: {LIBREOFFICE_PATH}")

    with tempfile.TemporaryDirectory() as tmpdir:
        docx_tmp = os.path.join(tmpdir, "document.docx")
        with open(docx_tmp, "wb") as f:
            f.write(signed_docx_bytes)

        result = subprocess.run(
            [LIBREOFFICE_PATH, "--headless", "--convert-to", "pdf",
             "--outdir", tmpdir, docx_tmp],
            capture_output=True, text=True
        )

        if result.returncode != 0:
            raise RuntimeError(f"LibreOffice error:\n{result.stderr}")

        pdf_path = os.path.join(tmpdir, "document.pdf")
        if not os.path.exists(pdf_path):
            raise FileNotFoundError("PDF tidak ditemukan setelah konversi LibreOffice.")

        with open(pdf_path, "rb") as f:
            return f.read()


def _convert_with_docx2pdf(signed_docx_bytes: bytes) -> bytes:
    import docx2pdf  # noqa: imported lazily as fallback
    with tempfile.TemporaryDirectory() as tmpdir:
        docx_tmp = os.path.join(tmpdir, "document.docx")
        pdf_tmp  = os.path.join(tmpdir, "document.pdf")
        with open(docx_tmp, "wb") as f:
            f.write(signed_docx_bytes)
        docx2pdf.convert(docx_tmp, pdf_tmp)
        with open(pdf_tmp, "rb") as f:
            return f.read()