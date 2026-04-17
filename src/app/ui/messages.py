from __future__ import annotations

from typing import Any


TEMPLATE_PROCESS_BUTTON = "✍️  Proses"


def get_step_1_send_document() -> str:
    return (
        "📄 *Langkah 1 — Kirim dokumen*\n\n"
        "Kirimkan file `.docx` atau `.pdf` yang ingin ditandatangani.\n"
        "_(Ketik /cancel untuk membatalkan)_"
    )


def get_active_process_warning() -> str:
    return "⏳ Ada proses yang sedang berjalan. Tunggu sebentar atau /cancel dulu."


def get_invalid_document_message() -> str:
    return "⚠️ Kirim file *.docx* atau *.pdf* ya, bukan jenis pesan lain."


def get_downloading_document() -> str:
    return "📥 Mengunduh dokumen..."


def get_document_received(file_name: str, is_docx: bool) -> str:
    doc_type_label = "Word (.docx)" if is_docx else "PDF"
    return (
        f"✅ *{file_name}* diterima! _{doc_type_label}_\n\n"
        "🖊 *Langkah 2 — Kirim file tanda tangan*\n\n"
        "• Format: PNG, JPG, atau SVG\n"
        "• Nama file = keyword pencarian\n"
        "• Kirim sebagai *File* (bukan Photo) agar tidak blur\n\n"
        "_(Ketik /cancel untuk membatalkan)_"
    )


def get_wait_docx_wrong_type(kind: str) -> str:
    mapping = {
        "photo": "📸 Ini foto, bukan dokumen. Kirim file *.docx* atau *.pdf* ya.",
        "video": "🎥 Ini video. Kirim file *.docx* atau *.pdf* ya.",
        "audio": "🎵 Ini audio. Kirim file *.docx* atau *.pdf* ya.",
        "sticker": "😄 Stiker keren, tapi aku butuh file *.docx* atau *.pdf*.",
        "unknown": "⚠️ Format tidak dikenal. Kirim file *.docx* atau *.pdf* ya.",
    }
    return mapping[kind]


def get_session_expired() -> str:
    return "⚠️ Sesi habis. Ketik /sign untuk mulai ulang."


def get_photo_signature_received() -> str:
    return (
        "✅ Tanda tangan diterima!\n\n"
        "💡 *Tips:* Lain kali kirim sebagai *File* (tekan 📎 → File) "
        "agar kualitasnya tidak turun karena kompresi Telegram."
    )


def get_wait_sign_wrong_type(kind: str) -> str:
    mapping = {
        "video": "🎥 Ini video. Kirim gambar tanda tangan ya _(PNG/JPG/SVG)_.",
        "audio": "🎵 Ini audio. Kirim gambar tanda tangan ya _(PNG/JPG/SVG)_.",
        "sticker": "😄 Kirim gambar tanda tangan ya, bukan stiker.",
        "document_again": (
            "📄 Sepertinya kamu kirim dokumen lagi.\n"
            "Sekarang gilirannya kirim *gambar tanda tangan* _(PNG/JPG/SVG)_."
        ),
        "unsupported_document": "⚠️ Format tidak didukung. Kirim gambar tanda tangan _(PNG/JPG/SVG)_.",
        "unknown": "⚠️ Kirim gambar tanda tangan _(PNG/JPG/SVG)_ ya.",
    }
    return mapping[kind]


def get_pdf_received_searching(keyword: str) -> str:
    return (
        "📄 Dokumen PDF diterima.\n"
        f"🔍 Mencari `{keyword}` di seluruh dokumen... mohon tunggu."
    )


def get_pdf_keyword_searching(keyword: str) -> str:
    return f"🔍 Mencari `{keyword}` di PDF... mohon tunggu."


def get_detecting_zones() -> str:
    return "🔍 Mendeteksi zona TTD..."


def get_processing_document() -> str:
    return "🔍 Memproses dokumen..."


def get_docx_keyword_not_found(keyword: str) -> str:
    return (
        "❌ *Keyword tidak ditemukan di dokumen.*\n\n"
        f"Keyword: `{keyword}`\n\n"
        "Pastikan nama file TTD mengandung kata yang ada di dokumen."
    )


def get_template_placeholder_found() -> str:
    return "✅ *[TEMPLATE]* Placeholder ditemukan!\n\nTekan tombol di bawah untuk proses."


def get_zone_selection_found(zone_count: int, keyword: str) -> str:
    return (
        f"✅ Ditemukan *{zone_count} zona* untuk keyword `{keyword}`.\n\n"
        "Pilih zona yang akan di-inject, lalu tekan *Proses*:"
    )


def get_detect_zones_failed(error: str) -> str:
    return f"❌ Gagal deteksi zona:\n`{error}`\n\nKetik /sign untuk mencoba lagi."


def get_processing_pdf() -> str:
    return "✍️ Menyisipkan tanda tangan di PDF..."


def get_pdf_keyword_not_found(keyword: str) -> str:
    return (
        "❌ *Keyword tidak ditemukan di dokumen PDF.*\n\n"
        f"🔍 Keyword yang dicari: `{keyword}`\n\n"
        "💡 *Tips:* Pastikan nama file TTD kamu mengandung kata yang ada di PDF.\n"
        "Contoh: jika nama di PDF `Farino Joshua`, beri nama file TTD `Farino Joshua.png`\n\n"
        "Ketik /sign untuk coba lagi."
    )


def get_success_pdf(doc_name: str, keyword: str, output_name: str) -> str:
    return (
        "✅ *Selesai! (PDF Bypass)*\n\n"
        f"📋 `{doc_name}`\n"
        f"🔑 Keyword: `{keyword}`\n"
        f"📎 `{output_name}`\n\n"
        "_Ketik /sign untuk dokumen berikutnya._"
    )


def get_pdf_processing_failed(error: str) -> str:
    return f"❌ *Gagal memproses PDF:*\n`{error}`\n\nKetik /sign untuk mencoba lagi."


def get_select_min_zone_alert() -> str:
    return "Pilih minimal 1 zona dulu!"


def get_processing_zones(count: int) -> str:
    return f"⚙️ Memproses {count} zona... mohon tunggu."


def get_docx_processing_status(zone_count: int, is_template: bool) -> str:
    if is_template:
        return "📋 [TEMPLATE] Mengkonversi DOCX ke PDF..."
    return f"✍️ Mengkonversi & Menyisipkan tanda tangan di {zone_count} zona..."


def get_conversion_queued() -> str:
    return (
        "⏳ *Server sedang memproses permintaan lain.*\n\n"
        "Konversimu masuk antrian dan akan diproses otomatis. "
        "Mohon tunggu sebentar..."
    )


def get_success_docx(
    doc_name: str,
    keyword: str,
    output_name: str,
    selected_zones: list[dict[str, Any]],
    is_template: bool,
) -> str:
    mode_label = "📋 Template" if is_template else f"🔍 Fallback ({len(selected_zones)} zona)"
    zone_summary = _build_zone_summary(selected_zones, keyword, is_template)
    return (
        f"✅ *Selesai! ({mode_label})*\n\n"
        f"📋 `{doc_name}`\n"
        f"🔑 Keyword: `{keyword}`\n"
        f"✍️ Tanda tangan:\n{zone_summary}\n\n"
        f"📎 `{output_name}`\n\n"
        "_Ketik /sign untuk dokumen berikutnya._"
    )


def get_docx_processing_failed(error: str) -> str:
    return f"❌ *Gagal memproses dokumen:*\n`{error}`\n\nKetik /sign untuk mencoba lagi."


def get_cancelled() -> str:
    return "🚫 Proses dibatalkan.\n\nKetik /sign untuk mulai lagi."


def get_fallback_text() -> str:
    return "Ketik /sign untuk mulai, atau tekan tombol di bawah."


def _build_zone_summary(
    selected_zones: list[dict[str, Any]],
    keyword: str,
    is_template: bool,
) -> str:
    if is_template:
        return f"  1. `{keyword}` (template placeholder • 100%)"

    zone_summary = "\n".join(
        f"  {index + 1}. `{(zone.get('matched_name') or keyword)[:45]}` "
        f"({zone['confidence']:.0%} · {_tier_label(zone['confidence'])})"
        for index, zone in enumerate(selected_zones[:6])
    )
    if len(selected_zones) > 6:
        zone_summary += f"\n  _...dan {len(selected_zones) - 6} zona lainnya_"
    return zone_summary


def _tier_label(confidence: float) -> str:
    if confidence >= 0.95:
        return "exact"
    if confidence >= 0.85:
        return "case-insensitive"
    return "partial"
