# api.py — Word Signer REST API
# Jalankan: uvicorn api:app --reload
# Docs:     http://localhost:8000/docs

import os
import tempfile

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse

from services.detector_service import detect_signature_zones
from services.converter_service import convert_to_pdf
from services.injector_service import inject_signature
from services.logger_service import log_success, log_error

app = FastAPI(
    title="Word Signer API",
    description="Upload DOCX + tanda tangan → dapat PDF signed balik.",
    version="1.0.0",
)


# ── Health check ─────────────────────────────────────────────
@app.get("/", summary="Health check")
def root():
    return {"status": "ok", "message": "Word Signer API is running."}


# ── Main endpoint ─────────────────────────────────────────────
@app.post("/sign", summary="Tanda tangani dokumen Word")
async def sign_document(
    doc: UploadFile = File(..., description="File Word (.docx)"),
    sign: UploadFile = File(..., description="File tanda tangan (png/jpg/svg)"),
    all_zones: bool = Form(True, description="Pakai semua zona yang ditemukan"),
    confidence: float = Form(0.4, description="Threshold confidence deteksi zona"),
):
    """
    Upload DOCX + file tanda tangan → dapat PDF signed.

    - **doc**: file `.docx`
    - **sign**: file tanda tangan `.png` / `.jpg` / `.svg`
    - **all_zones**: `true` = pakai semua zona (default), `false` = hanya zona pertama
    - **confidence**: threshold deteksi zona (default `0.4`)

    Response: file PDF binary (`application/pdf`)
    """
    # Validasi ekstensi
    if not doc.filename.lower().endswith(".docx"):
        raise HTTPException(400, detail="File dokumen harus berformat .docx")

    sign_ext = sign.filename.rsplit(".", 1)[-1].lower()
    if sign_ext not in ["png", "jpg", "jpeg", "svg"]:
        raise HTTPException(400, detail="File tanda tangan harus png/jpg/jpeg/svg")

    with tempfile.TemporaryDirectory() as tmpdir:
        # Simpan upload ke tempdir
        docx_path = os.path.join(tmpdir, doc.filename)
        sign_path = os.path.join(tmpdir, sign.filename)

        docx_bytes = await doc.read()
        sign_bytes = await sign.read()

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
            raise HTTPException(
                422,
                detail="Zona tanda tangan tidak ditemukan. "
                       "Pastikan nama file TTD cocok dengan jabatan di dokumen."
            )

        # 2. Pilih zona
        selected_zones = zones if all_zones else zones[:1]

        # 3. Convert DOCX → PDF
        try:
            pdf_bytes = convert_to_pdf(docx_bytes)
        except Exception as e:
            log_error(docx_path, str(e))
            raise HTTPException(500, detail=f"Gagal konversi PDF: {e}")

        # 4. Inject signature
        try:
            signed_pdf = inject_signature(pdf_bytes, sign_path, selected_zones)
        except Exception as e:
            log_error(docx_path, str(e))
            raise HTTPException(500, detail=f"Gagal inject TTD: {e}")

        # 5. Simpan output & kirim balik
        output_name = doc.filename.replace(".docx", "_signed.pdf")
        output_path = os.path.join(tmpdir, output_name)

        with open(output_path, "wb") as f:
            f.write(signed_pdf)

        log_success(docx_path, output_path, len(selected_zones))

        # Baca ulang sebelum tempdir dihapus
        with open(output_path, "rb") as f:
            final_pdf = f.read()

    # Kirim PDF sebagai response
    import io
    from fastapi.responses import StreamingResponse
    return StreamingResponse(
        io.BytesIO(final_pdf),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{output_name}"'},
    )


# ── Zones preview endpoint ────────────────────────────────────
@app.post("/zones", summary="Preview zona tanda tangan (tanpa proses)")
async def preview_zones(
    doc: UploadFile = File(..., description="File Word (.docx)"),
    sign: UploadFile = File(..., description="File tanda tangan (png/jpg/svg)"),
    confidence: float = Form(0.4),
):
    """
    Detect zona TTD tanpa proses signing.
    Berguna untuk preview sebelum `/sign`.
    """
    if not doc.filename.lower().endswith(".docx"):
        raise HTTPException(400, detail="File dokumen harus berformat .docx")

    with tempfile.TemporaryDirectory() as tmpdir:
        docx_path = os.path.join(tmpdir, doc.filename)
        sign_path = os.path.join(tmpdir, sign.filename)

        with open(docx_path, "wb") as f:
            f.write(await doc.read())
        with open(sign_path, "wb") as f:
            f.write(await sign.read())

        try:
            zones = detect_signature_zones(
                docx_path, sign_path,
                confidence_threshold=confidence,
            )
        except Exception as e:
            raise HTTPException(500, detail=str(e))

    return {
        "total": len(zones),
        "zones": [
            {
                "index": i,
                "matched_name": z.get("matched_name"),
                "confidence": z.get("confidence"),
                "context": z.get("context"),
            }
            for i, z in enumerate(zones)
        ],
    }