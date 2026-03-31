# api.py — Word Signer REST API
# Jalankan: uvicorn api:app --reload
# Docs:     http://localhost:8000/docs

import io
import os
import tempfile

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import StreamingResponse

from services.detector_service import detect_signature_zones
from services.converter_service import convert_to_pdf
from services.injector_service import inject_signature
from services.logger_service import log_success, log_error

app = FastAPI(
    title="Word Signer API",
    description=(
        "Upload DOCX + file tanda tangan → terima PDF signed.\n\n"
        "Nama file tanda tangan digunakan sebagai keyword pencarian di dokumen.\n"
        "Contoh: `firano.png` → cari kata _firano_ di dokumen."
    ),
    version="2.0.0",
)


# ── Health check ─────────────────────────────────────────────
@app.get("/", summary="Health check")
def root():
    return {"status": "ok", "message": "Word Signer API is running.", "version": "2.0.0"}


# ── POST /sign ────────────────────────────────────────────────
@app.post("/sign", summary="Tanda tangani dokumen Word")
async def sign_document(
    doc: UploadFile  = File(..., description="File Word (.docx)"),
    sign: UploadFile = File(..., description="File tanda tangan (png/jpg/svg). Nama file = keyword pencarian."),
    all_zones: bool  = Form(True,  description="True = inject semua zona valid, False = zona pertama saja"),
    confidence: float = Form(0.4,  description="Threshold confidence deteksi (0.0–1.0, default 0.4)"),
):
    """
    Upload DOCX + file tanda tangan → terima PDF signed.

    **Cara kerja keyword:**
    - Nama file tanda tangan (tanpa ekstensi) digunakan sebagai keyword
    - Detector mencari keyword di dokumen dengan 3 tier:
      1. Exact match (case-sensitive) → confidence 1.0
      2. Case-insensitive full phrase → confidence 0.9
      3. Partial per kata (≥60% match) → confidence 0.5–0.85
    - Semua lokasi valid yang ditemukan akan di-inject (jika `all_zones=true`)

    **Response:** file PDF binary (`application/pdf`)
    """
    # Validasi ekstensi
    if not doc.filename.lower().endswith(".docx"):
        raise HTTPException(400, detail="File dokumen harus berformat .docx")

    sign_ext = sign.filename.rsplit(".", 1)[-1].lower()
    if sign_ext not in ["png", "jpg", "jpeg", "svg"]:
        raise HTTPException(400, detail="File tanda tangan harus png/jpg/jpeg/svg")

    if not 0.0 <= confidence <= 1.0:
        raise HTTPException(400, detail="Confidence harus antara 0.0 dan 1.0")

    docx_bytes = await doc.read()
    sign_bytes = await sign.read()

    with tempfile.TemporaryDirectory() as tmpdir:
        docx_path = os.path.join(tmpdir, doc.filename)
        sign_path = os.path.join(tmpdir, sign.filename)

        with open(docx_path, "wb") as f:
            f.write(docx_bytes)
        with open(sign_path, "wb") as f:
            f.write(sign_bytes)

        # 1. Detect zones
        try:
            zones = detect_signature_zones(
                docx_path, sign_path,
                confidence_threshold=confidence,
            )
        except Exception as e:
            log_error(docx_path, str(e))
            raise HTTPException(500, detail=f"Gagal deteksi zona: {e}")

        if not zones:
            keyword = os.path.splitext(sign.filename)[0]
            raise HTTPException(
                422,
                detail=(
                    f"Keyword '{keyword}' tidak ditemukan di dokumen. "
                    "Pastikan nama file TTD mengandung kata/frasa yang ada di dokumen."
                ),
            )

        # 2. Pilih zona
        selected_zones = zones if all_zones else zones[:1]

        # 3. Convert DOCX → PDF
        try:
            pdf_bytes = convert_to_pdf(docx_bytes)
        except Exception as e:
            log_error(docx_path, str(e))
            raise HTTPException(500, detail=f"Gagal konversi PDF: {e}")

        # 4. Inject TTD
        try:
            signed_pdf = inject_signature(pdf_bytes, sign_path, selected_zones)
        except Exception as e:
            log_error(docx_path, str(e))
            raise HTTPException(500, detail=f"Gagal inject TTD: {e}")

        log_success(docx_path, "api_output", len(selected_zones))

    output_name = doc.filename.replace(".docx", "_signed.pdf")
    return StreamingResponse(
        io.BytesIO(signed_pdf),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{output_name}"'},
    )


# ── POST /zones ───────────────────────────────────────────────
@app.post("/zones", summary="Preview zona TTD tanpa proses signing")
async def preview_zones(
    doc: UploadFile   = File(..., description="File Word (.docx)"),
    sign: UploadFile  = File(..., description="File tanda tangan (png/jpg/svg)"),
    confidence: float = Form(0.4),
):
    """
    Detect zona TTD tanpa melakukan signing.
    Berguna untuk preview / debug sebelum memanggil `/sign`.

    Response JSON berisi list zona yang ditemukan beserta confidence score-nya.
    """
    if not doc.filename.lower().endswith(".docx"):
        raise HTTPException(400, detail="File dokumen harus berformat .docx")

    if not 0.0 <= confidence <= 1.0:
        raise HTTPException(400, detail="Confidence harus antara 0.0 dan 1.0")

    docx_bytes = await doc.read()
    sign_bytes = await sign.read()

    with tempfile.TemporaryDirectory() as tmpdir:
        docx_path = os.path.join(tmpdir, doc.filename)
        sign_path = os.path.join(tmpdir, sign.filename)

        with open(docx_path, "wb") as f:
            f.write(docx_bytes)
        with open(sign_path, "wb") as f:
            f.write(sign_bytes)

        try:
            zones = detect_signature_zones(
                docx_path, sign_path,
                confidence_threshold=confidence,
            )
        except Exception as e:
            raise HTTPException(500, detail=str(e))

    keyword = os.path.splitext(sign.filename)[0]
    return {
        "keyword": keyword,
        "total":   len(zones),
        "zones": [
            {
                "index":          i,
                "matched_name":   z.get("matched_name"),
                "keyword":        z.get("keyword"),
                "confidence":     z.get("confidence"),
                "inject_position": z.get("inject_position"),
                "context":        z.get("context"),
            }
            for i, z in enumerate(zones)
        ],
    }