import os
import io
import asyncio
import logging
import tempfile
import fitz
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ChatAction
from telegram.ext import (
    CommandHandler, MessageHandler, ConversationHandler, CallbackQueryHandler, ContextTypes, filters
)
from services.detector_service import detect_signature_zones
from services.converter_service import convert_to_pdf
from services.injector_service import inject_signature
from services.docx_injector_service import inject_signature_to_docx, PlaceholderNotFoundError
from repositories import LogRepository
from repositories.session_repository import session_manager
from handlers.core_handler import _kb_start, CB_START_SIGN

logger = logging.getLogger(__name__)
log_repo = LogRepository()

WAIT_DOCX, WAIT_SIGN, WAIT_ZONE_SELECT, WAIT_KEYWORD = range(4)

# ── Callback data ─────────────────────────────────────────────
CB_ZONE_TOGGLE  = "zt"
CB_ZONE_ALL     = "za"
CB_ZONE_CONFIRM = "zc"
CB_START_SIGN   = "start_sign"

# ── In-memory storage ─────────────────────────────────────────
user_sessions: dict = {}
active_users:  set  = set()

MAX_FILE_BYTES = 20 * 1024 * 1024  # 20 MB


# ── Helpers ───────────────────────────────────────────────────

def _tier_label(conf: float) -> str:
    if conf >= 0.95: return "exact"
    if conf >= 0.85: return "case-insensitive"
    return "partial"


def _pdf_pages_to_scan(total: int) -> list[int]:
    """
    Performance limiter untuk PDF bypass.
    Scan hanya page 0 + 2 halaman terakhir, deduplicated & sorted.
    """
    pages = {0, max(0, total - 2), max(0, total - 1)}
    return sorted(pages)


# ── Keyboards ─────────────────────────────────────────────────

def _kb_start() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("✍️  Mulai tanda tangan", callback_data=CB_START_SIGN),
    ]])


def _kb_zones(zones: list, selected: set) -> InlineKeyboardMarkup:
    rows = []
    for i, z in enumerate(zones):
        name  = (z.get("matched_name") or z.get("keyword") or f"Zona {i+1}")[:35]
        conf  = z["confidence"]
        check = "✅" if i in selected else "⬜"
        label = f"{check} {name} ({conf:.0%} · {_tier_label(conf)})"
        rows.append([InlineKeyboardButton(label, callback_data=f"{CB_ZONE_TOGGLE}:{i}")])

    rows.append([
        InlineKeyboardButton("☑️  Pilih semua", callback_data=CB_ZONE_ALL),
        InlineKeyboardButton(
            f"✍️  Proses ({len(selected)} zona)",
            callback_data=CB_ZONE_CONFIRM,
        ),
    ])
    return InlineKeyboardMarkup(rows)








# ── Button handler ────────────────────────────────────────────
async def handle_start_button(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_reply_markup(reply_markup=None)

    await query.message.reply_text(
        "📄 *Langkah 1 — Kirim dokumen*\n\n"
        "Kirimkan file `.docx` atau `.pdf` yang ingin ditandatangani.\n"
        "_(Ketik /cancel untuk membatalkan)_",
        parse_mode="Markdown",
    )
    return WAIT_DOCX


# ── /sign ─────────────────────────────────────────────────────
async def cmd_sign(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id in session_manager._active_users:
        await update.message.reply_text(
            "⏳ Ada proses yang sedang berjalan. Tunggu sebentar atau /cancel dulu."
        )
        return WAIT_DOCX

    await update.message.reply_text(
        "📄 *Langkah 1 — Kirim dokumen*\n\n"
        "Kirimkan file `.docx` atau `.pdf` yang ingin ditandatangani.\n"
        "_(Ketik /cancel untuk membatalkan)_",
        parse_mode="Markdown",
    )
    return WAIT_DOCX




# ═══════════════════════════════════════════════════════════════
# STATE: WAIT_DOCX
# ═══════════════════════════════════════════════════════════════

async def receive_docx(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Terima DOCX atau PDF. Tolak file lain, stay di state."""
    msg = update.message
    doc = msg.document

    # Tidak ada document sama sekali (harusnya tidak terjadi tapi jaga-jaga)
    if not doc:
        await msg.reply_text(
            "⚠️ Kirim file *.docx* atau *.pdf* ya, bukan jenis pesan lain.",
            parse_mode="Markdown",
        )
        return WAIT_DOCX

    filename = (doc.file_name or "").lower()
    is_docx  = filename.endswith(".docx")
    is_pdf   = filename.endswith(".pdf")

    if not (is_docx or is_pdf):
        await msg.reply_text(
            "❌ Format tidak didukung.\n\n"
            "Kirim file *.docx* atau *.pdf* ya. "
            "Format seperti `.doc`, `.xls`, dll belum didukung.",
            parse_mode="Markdown",
        )
        return WAIT_DOCX  # Stay, jangan reset sesi

    # File size gate
    if doc.file_size and doc.file_size > MAX_FILE_BYTES:
        await msg.reply_text(
            "❌ File terlalu besar (maks 20MB).\n"
            "Untuk PDF besar, coba compress dulu ya."
        )
        return WAIT_DOCX

    status = await msg.reply_text("📥 Mengunduh dokumen...")
    file   = await doc.get_file()
    buf    = io.BytesIO()
    await file.download_to_memory(buf)
    buf.seek(0)

    user_id = update.effective_user.id
    session_manager._user_sessions[user_id] = {
        "doc_bytes":    buf.read(),
        "doc_name":     doc.file_name,
        "doc_type":     "docx" if is_docx else "pdf",
                "chat_id":      update.effective_chat.id,
    }

    doc_type_label = "Word (.docx)" if is_docx else "PDF"
    await status.edit_text(
        f"✅ *{doc.file_name}* diterima! _{doc_type_label}_\n\n"
        "🖊 *Langkah 2 — Kirim file tanda tangan*\n\n"
        "• Format: PNG, JPG, atau SVG\n"
        "• Nama file = keyword pencarian\n"
        "• Kirim sebagai *File* (bukan Photo) agar tidak blur\n\n"
        "_(Ketik /cancel untuk membatalkan)_",
        parse_mode="Markdown",
    )
    return WAIT_SIGN


async def reject_wrong_type_in_docx(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """
    Handler untuk Photo/Video/Audio/Sticker yang nyasar ke WAIT_DOCX.
    Tolak dengan ramah, JANGAN reset state.
    """
    msg = update.message

    if msg.photo:
        reply = "📸 Ini foto, bukan dokumen. Kirim file *.docx* atau *.pdf* ya."
    elif msg.video:
        reply = "🎥 Ini video. Kirim file *.docx* atau *.pdf* ya."
    elif msg.audio or msg.voice:
        reply = "🎵 Ini audio. Kirim file *.docx* atau *.pdf* ya."
    elif msg.sticker:
        reply = "😄 Stiker keren, tapi aku butuh file *.docx* atau *.pdf*."
    else:
        reply = "⚠️ Format tidak dikenal. Kirim file *.docx* atau *.pdf* ya."

    await msg.reply_text(reply, parse_mode="Markdown")
    return WAIT_DOCX  # ← KUNCI: state tidak direset


# ═══════════════════════════════════════════════════════════════
# STATE: WAIT_SIGN
# ═══════════════════════════════════════════════════════════════

async def receive_sign_as_document(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """TTD dikirim sebagai File/Document — kualitas HD, jalur ideal."""
    msg  = update.message
    doc  = msg.document
    mime = (doc.mime_type or "") if doc else ""

    if not doc or not mime.startswith("image/"):
        await msg.reply_text(
            "⚠️ File ini bukan gambar. Kirim gambar tanda tangan ya "
            "_(PNG, JPG, atau SVG)_.",
            parse_mode="Markdown",
        )
        return WAIT_SIGN

    ext = (doc.file_name or "file.png").rsplit(".", 1)[-1].lower()
    if ext not in ["png", "jpg", "jpeg", "svg"]:
        await msg.reply_text(
            "❌ Format tanda tangan harus *PNG, JPG, atau SVG*.",
            parse_mode="Markdown",
        )
        return WAIT_SIGN

    buf = io.BytesIO()
    tg_file = await doc.get_file()
    await tg_file.download_to_memory(buf)
    buf.seek(0)

    user_id = update.effective_user.id
    session = session_manager.get_session(user_id)
    if not session:
        await msg.reply_text("⚠️ Sesi habis. Ketik /sign untuk mulai ulang.")
        return ConversationHandler.END

    session["sign_bytes"] = buf.read()
    session["sign_name"]  = doc.file_name or "signature.png"

    return await _after_sign_received(update, ctx)


async def receive_sign_as_photo(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """
    TTD dikirim sebagai Photo (compressed).
    Diterima dengan tip, tidak ditolak.
    """
    msg     = update.message
    user_id = update.effective_user.id
    session = session_manager.get_session(user_id)

    if not session:
        await msg.reply_text("⚠️ Sesi habis. Ketik /sign untuk mulai ulang.")
        return ConversationHandler.END

    # Ambil resolusi tertinggi
    best = max(msg.photo, key=lambda p: p.file_size or 0)
    buf  = io.BytesIO()
    tg_file = await best.get_file()
    await tg_file.download_to_memory(buf)
    buf.seek(0)

    session["sign_bytes"] = buf.read()
    session["sign_name"]  = "signature.jpg"

    # Kasih tip tapi jangan halangi proses
    await msg.reply_text(
        "✅ Tanda tangan diterima!\n\n"
        "💡 *Tips:* Lain kali kirim sebagai *File* (tekan 📎 → File) "
        "agar kualitasnya tidak turun karena kompresi Telegram.",
        parse_mode="Markdown",
    )

    return await _after_sign_received(update, ctx)


async def reject_wrong_type_in_sign(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Tolak non-gambar di WAIT_SIGN, stay di state."""
    msg = update.message

    if msg.video:
        reply = "🎥 Ini video. Kirim gambar tanda tangan ya _(PNG/JPG/SVG)_."
    elif msg.audio or msg.voice:
        reply = "🎵 Ini audio. Kirim gambar tanda tangan ya _(PNG/JPG/SVG)_."
    elif msg.sticker:
        reply = "😄 Kirim gambar tanda tangan ya, bukan stiker."
    elif msg.document:
        ext = (msg.document.file_name or "").rsplit(".", 1)[-1].lower()
        if ext in ["docx", "pdf", "doc"]:
            reply = (
                "📄 Sepertinya kamu kirim dokumen lagi.\n"
                "Sekarang gilirannya kirim *gambar tanda tangan* _(PNG/JPG/SVG)_."
            )
        else:
            reply = "⚠️ Format tidak didukung. Kirim gambar tanda tangan _(PNG/JPG/SVG)_."
    else:
        reply = "⚠️ Kirim gambar tanda tangan _(PNG/JPG/SVG)_ ya."

    await msg.reply_text(reply, parse_mode="Markdown")
    return WAIT_SIGN  # Stay


async def _after_sign_received(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """
    Branch setelah TTD diterima:
    - PDF  → tanya keyword dulu (WAIT_KEYWORD)
    - DOCX → langsung proses
    """
    user_id = update.effective_user.id
    session = session_manager._user_sessions[user_id]
    doc_type = session["doc_type"]

    if doc_type == "pdf":
        await update.message.reply_text(
            "📝 Dokumen kamu adalah *PDF*.\n\n"
            "Ketik *nama* atau *jabatan* target penanda tangan.\n"
            "Contoh: `Kepala Divisi IT` atau `Direktur Utama`\n\n"
            "⚠️ Minimal 3 karakter. Ketik /cancel untuk batal.",
            parse_mode="Markdown",
        )
        return WAIT_KEYWORD

    # DOCX → langsung ke deteksi & zone selection
    return await _run_docx_detect(update, ctx)


# ═══════════════════════════════════════════════════════════════
# STATE: WAIT_KEYWORD (PDF only)
# ═══════════════════════════════════════════════════════════════

async def receive_keyword(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Terima keyword dari user untuk PDF bypass."""
    msg     = update.message
    keyword = (msg.text or "").strip()

    # Validator
    if not keyword or len(keyword) < 3:
        await msg.reply_text(
            "⚠️ Keyword terlalu pendek. Minimal 3 karakter.\n"
            "Contoh: `Kepala Divisi IT`",
            parse_mode="Markdown",
        )
        return WAIT_KEYWORD

    user_id = update.effective_user.id
    session = session_manager.get_session(user_id)
    if not session:
        await msg.reply_text("⚠️ Sesi habis. Ketik /sign untuk mulai ulang.")
        return ConversationHandler.END

    session["keyword"]    = keyword
    session["sign_name"]  = session.get("sign_name", "signature.png")

    status = await msg.reply_text(
        f"🔍 Mencari `{keyword}` di PDF... mohon tunggu.",
        parse_mode="Markdown",
    )
    await ctx.bot.send_chat_action(
        chat_id=update.effective_chat.id,
        action=ChatAction.UPLOAD_DOCUMENT,
    )

    return await _run_pdf_bypass(update, ctx, status)


# ═══════════════════════════════════════════════════════════════
# DOCX PIPELINE
# ═══════════════════════════════════════════════════════════════

async def _run_docx_detect(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """
    Detect zones di DOCX (template mode dulu, fallback ke detector).
    Tampilkan zone selection dialog.
    """
    user_id = update.effective_user.id
    session = session_manager._user_sessions[user_id]
    msg     = await update.message.reply_text("🔍 Mendeteksi zona TTD...")

    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            docx_path = os.path.join(tmpdir, session["doc_name"])
            sign_path = os.path.join(tmpdir, session["sign_name"])

            with open(docx_path, "wb") as f:
                f.write(session["doc_bytes"])
            with open(sign_path, "wb") as f:
                f.write(session["sign_bytes"])

            keyword = os.path.splitext(session["sign_name"])[0]
            zones   = []

            # ── Template mode (primary) ──
            try:
                await msg.edit_text("📋 Mencari placeholder template...")
                modified_docx = inject_signature_to_docx(
                    session["doc_bytes"], sign_path, keyword
                )
                session["template_mode"] = True
                session["modified_docx"] = modified_docx
                zones = [{"matched_name": keyword, "confidence": 1.0, "keyword": keyword}]
                logger.info(f"[{user_id}] Template mode detected")

            except PlaceholderNotFoundError:
                # ── Detector fallback ──
                await msg.edit_text("🔍 Mencari zona TTD dengan detector...")
                loop  = asyncio.get_event_loop()
                zones = await loop.run_in_executor(
                    None, detect_signature_zones, docx_path, sign_path, 0.4
                )
                session["template_mode"] = False
                logger.info(f"[{user_id}] Detection fallback: {len(zones)} zones")

        session["keyword"]  = keyword
        session["zones"]    = zones
        session["selected"] = set(range(len(zones)))

        if not zones:
            await msg.edit_text(
                f"❌ *Keyword tidak ditemukan di dokumen.*\n\n"
                f"Keyword: `{keyword}`\n\n"
                "Pastikan nama file TTD mengandung kata yang ada di dokumen.",
                parse_mode="Markdown",
            )
            session_manager.clear_session(user_id, None)
            return ConversationHandler.END

        

        # Template mode: skip zone selection
        if session.get("template_mode"):
            await msg.edit_text(
                "✅ *[TEMPLATE]* Placeholder ditemukan!\n\nTekan tombol di bawah untuk proses.",
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("✍️  Proses", callback_data=CB_ZONE_CONFIRM)
                ]]),
            )
            return WAIT_ZONE_SELECT

        # Normal detector: zone selection
        await msg.edit_text(
            f"✅ Ditemukan *{len(zones)} zona* untuk keyword `{keyword}`.\n\n"
            "Pilih zona yang akan di-inject, lalu tekan *Proses*:",
            parse_mode="Markdown",
            reply_markup=_kb_zones(zones, session["selected"]),
        )
        return WAIT_ZONE_SELECT

    except Exception as e:
        logger.exception("Error saat detect zones")
        await msg.edit_text(
            f"❌ Gagal deteksi zona:\n`{e}`\n\nKetik /sign untuk mencoba lagi.",
            parse_mode="Markdown",
        )
        session_manager.clear_session(user_id, None)
        return ConversationHandler.END


# ═══════════════════════════════════════════════════════════════
# PDF BYPASS PIPELINE
# ═══════════════════════════════════════════════════════════════

async def _run_pdf_bypass(
    update: Update, ctx: ContextTypes.DEFAULT_TYPE, status_msg
):
    """
    PDF bypass: skip detector & LibreOffice.
    Scan hanya page 0 + 2 halaman terakhir.
    """
    user_id = update.effective_user.id
    session = session_manager.get_session(user_id)
    if not session:
        return ConversationHandler.END

    keyword   = session["keyword"]
    doc_name  = session["doc_name"]
    chat_id   = session["chat_id"]
    success   = False

    session_manager.add_active_user(user_id)
    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            sign_path  = os.path.join(tmpdir, session["sign_name"])
            output_path = os.path.join(tmpdir, "output_signed.pdf")

            with open(sign_path, "wb") as f:
                f.write(session["sign_bytes"])

            doc_bytes = session["doc_bytes"]

            # Hitung halaman yang di-scan
            loop         = asyncio.get_event_loop()
            total_pages  = await loop.run_in_executor(
                None, _count_pdf_pages, doc_bytes
            )
            pages_to_scan = _pdf_pages_to_scan(total_pages)

            await status_msg.edit_text(
                f"✍️ Menyisipkan tanda tangan di halaman "
                f"{', '.join(str(p+1) for p in pages_to_scan)}..."
            )

            # Jalankan inject di executor (tidak block event loop)
            signed_pdf = await loop.run_in_executor(
                None,
                _sync_pdf_bypass,
                doc_bytes, sign_path, keyword, pages_to_scan
            )

        if signed_pdf is None:
            # Keyword tidak ditemukan — tawarkan retry keyword
            await status_msg.edit_text(
                f"❌ Keyword *`{keyword}`* tidak ditemukan di halaman yang di-scan.\n\n"
                "Ketik keyword lain untuk dicoba lagi, atau /cancel untuk batal.",
                parse_mode="Markdown",
            )
            # Kembali ke WAIT_KEYWORD agar user bisa coba keyword lain
            return WAIT_KEYWORD

        # Kirim hasil PDF
        output_name = doc_name.replace(".pdf", "_signed.pdf")
        if not output_name.endswith(".pdf"):
            output_name += "_signed.pdf"

        await ctx.bot.send_document(
            chat_id=chat_id,
            document=io.BytesIO(signed_pdf),
            filename=output_name,
            caption=(
                f"✅ *Selesai! (PDF Bypass)*\n\n"
                f"📋 `{doc_name}`\n"
                f"🔑 Keyword: `{keyword}`\n"
                f"📎 `{output_name}`\n\n"
                "_Ketik /sign untuk dokumen berikutnya._"
            ),
            parse_mode="Markdown",
            read_timeout=60,
            write_timeout=60,
            connect_timeout=60,
            pool_timeout=60,
        )

        try:
            await status_msg.delete()
        except Exception:
            pass

        log_repo.log_success(doc_name, "telegram_pdf_bypass", 1)
        success = True

    except Exception as e:
        logger.exception(f"Error PDF bypass user {user_id}")
        log_repo.log_error(doc_name, str(e))
        try:
            await status_msg.edit_text(
                f"❌ *Gagal memproses PDF:*\n`{e}`\n\n"
                "Ketik /sign untuk mencoba lagi.",
                parse_mode="Markdown",
            )
        except Exception:
            pass

    finally:
        session_manager.remove_active_user(user_id)
        session_manager.clear_session(user_id, None)

    return ConversationHandler.END


def _count_pdf_pages(doc_bytes: bytes) -> int:
    """Sync helper: hitung jumlah halaman PDF."""
    doc = fitz.open(stream=doc_bytes, filetype="pdf")
    n   = len(doc)
    doc.close()
    return n


def _sync_pdf_bypass(
    doc_bytes: bytes,
    sign_path: str,
    keyword: str,
    page_indices: list[int],
) -> bytes | None:
    """
    Sync worker untuk PDF bypass (dijalankan di executor).
    Return signed PDF bytes, atau None jika keyword tidak ditemukan.
    """
    # Buat zone hint yang kompatibel dengan inject_signature
    zones = [{
        "matched_name":    keyword,
        "keyword":         keyword,
        "confidence":      1.0,
        "inject_position": "above_same",
        "source":          "pdf_bypass",
        "table_location":  None,
        "paragraph_index": 0,
    }]

    # inject_signature sudah pakai pdf_placer yang scan berdasarkan keyword
    # Kita perlu limit scan ke page_indices saja
    # Wrap fitz.open dan override halaman yang diproses
    doc = fitz.open(stream=doc_bytes, filetype="pdf")

    # Validasi: pastikan keyword ada di salah satu halaman target
    keyword_found = False
    for page_idx in page_indices:
        if page_idx >= len(doc):
            continue
        page = doc[page_idx]
        if page.search_for(keyword):
            keyword_found = True
            break

    doc.close()

    if not keyword_found:
        return None

    # Inject via existing inject_signature dengan full doc_bytes
    # pdf_placer akan find keyword di seluruh dokumen — kita sudah validasi
    # keyword ada, jadi ini aman
    try:
        return inject_signature(doc_bytes, sign_path, zones)
    except Exception as e:
        logger.error(f"[PDF_BYPASS] inject failed: {e}")
        raise


# ═══════════════════════════════════════════════════════════════
# STATE: WAIT_ZONE_SELECT (DOCX only)
# ═══════════════════════════════════════════════════════════════

async def handle_zone_select(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query   = update.callback_query
    user_id = update.effective_user.id
    await query.answer()

    session = session_manager.get_session(user_id)
    if not session:
        await query.edit_message_text("⚠️ Sesi habis. Ketik /sign untuk mulai ulang.")
        return ConversationHandler.END

    zones    = session["zones"]
    selected = session["selected"]
    data     = query.data

    if data.startswith(f"{CB_ZONE_TOGGLE}:"):
        idx = int(data.split(":")[1])
        selected.discard(idx) if idx in selected else selected.add(idx)
        await query.edit_message_reply_markup(reply_markup=_kb_zones(zones, selected))
        return WAIT_ZONE_SELECT

    if data == CB_ZONE_ALL:
        if len(selected) == len(zones):
            selected.clear()
        else:
            selected.update(range(len(zones)))
        await query.edit_message_reply_markup(reply_markup=_kb_zones(zones, selected))
        return WAIT_ZONE_SELECT

    if data == CB_ZONE_CONFIRM:
        if not selected:
            await query.answer("Pilih minimal 1 zona dulu!", show_alert=True)
            return WAIT_ZONE_SELECT

        await query.edit_message_text(
            f"⚙️ Memproses {len(selected)} zona... mohon tunggu."
        )
        return await _process_docx(update, ctx, query.message)


# ═══════════════════════════════════════════════════════════════
# DOCX PROCESSING (convert + inject)
# ═══════════════════════════════════════════════════════════════

async def _process_docx(update: Update, ctx: ContextTypes.DEFAULT_TYPE, status_msg):
    """Convert DOCX → inject TTD → kirim PDF ke user."""
    user_id = update.effective_user.id
    session = session_manager.get_session(user_id)
    if not session:
        return ConversationHandler.END

    session_manager.add_active_user(user_id)

    doc_name       = session["doc_name"]
    sign_name      = session["sign_name"]
    sign_bytes     = session["sign_bytes"]
    zones          = session["zones"]
    selected       = session["selected"]
    selected_zones = [zones[i] for i in sorted(selected)]
    keyword        = session.get("keyword", os.path.splitext(sign_name)[0])
    chat_id        = session["chat_id"]
    is_template    = session.get("template_mode", False)
    success        = False

    try:
        loop = asyncio.get_event_loop()

        with tempfile.TemporaryDirectory() as tmpdir:
            sign_path = os.path.join(tmpdir, sign_name)
            with open(sign_path, "wb") as f:
                f.write(sign_bytes)

            if is_template:
                await status_msg.edit_text("📋 [TEMPLATE] Mengkonversi DOCX ke PDF...")
                signed_pdf = await loop.run_in_executor(
                    None, convert_to_pdf, session["modified_docx"]
                )
            else:
                await status_msg.edit_text("📄 Mengkonversi dokumen ke PDF...")
                pdf_bytes = await loop.run_in_executor(
                    None, convert_to_pdf, session["doc_bytes"]
                )

                await status_msg.edit_text(
                    f"✍️ Menyisipkan tanda tangan di {len(selected_zones)} zona..."
                )
                signed_pdf = await loop.run_in_executor(
                    None, inject_signature, pdf_bytes, sign_path, selected_zones
                )

        output_name  = doc_name.replace(".docx", "_signed.pdf")
        mode_label   = "📋 Template" if is_template else f"🔍 Fallback ({len(selected_zones)} zona)"

        if is_template:
            zone_summary = f"  1. `{keyword}` (template placeholder • 100%)"
        else:
            zone_summary = "\n".join(
                f"  {i+1}. `{(z.get('matched_name') or keyword)[:45]}` "
                f"({z['confidence']:.0%} · {_tier_label(z['confidence'])})"
                for i, z in enumerate(selected_zones[:6])
            )
            if len(selected_zones) > 6:
                zone_summary += f"\n  _...dan {len(selected_zones) - 6} zona lainnya_"

        await ctx.bot.send_document(
            chat_id=chat_id,
            document=io.BytesIO(signed_pdf),
            filename=output_name,
            caption=(
                f"✅ *Selesai! ({mode_label})*\n\n"
                f"📋 `{doc_name}`\n"
                f"🔑 Keyword: `{keyword}`\n"
                f"✍️ Tanda tangan:\n{zone_summary}\n\n"
                f"📎 `{output_name}`\n\n"
                "_Ketik /sign untuk dokumen berikutnya._"
            ),
            parse_mode="Markdown",
            read_timeout=60,
            write_timeout=60,
            connect_timeout=60,
            pool_timeout=60,
        )

        try:
            await status_msg.delete()
        except Exception:
            pass

        n_zones = 1 if is_template else len(selected_zones)
        log_repo.log_success(doc_name, "telegram_output", n_zones)
        success = True

    except Exception as e:
        logger.exception("Error saat proses dokumen")
        log_repo.log_error(doc_name, str(e))
        try:
            await status_msg.edit_text(
                f"❌ *Gagal memproses dokumen:*\n`{e}`\n\n"
                "Ketik /sign untuk mencoba lagi.",
                parse_mode="Markdown",
            )
        except Exception:
            pass

    finally:
        session_manager.remove_active_user(user_id)
        n_zones = 1 if is_template else len(selected_zones)
        session_manager.clear_session(user_id, None)

    return ConversationHandler.END


# ── /cancel ───────────────────────────────────────────────────
async def cmd_cancel(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    session_manager.clear_session(user_id, None)
    session_manager.remove_active_user(user_id)
    ctx.user_data.clear()
    await update.message.reply_text(
        "🚫 Proses dibatalkan.\n\nKetik /sign untuk mulai lagi.",
        reply_markup=_kb_start(),
    )
    return ConversationHandler.END


# ── Fallback ──────────────────────────────────────────────────
async def fallback_text(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Ketik /sign untuk mulai, atau tekan tombol di bawah.",
        reply_markup=_kb_start(),
    )


# ── Main ──────────────────────────────────────────────────────


def setup_workflow_handler(app):
    conv = ConversationHandler(
        entry_points=[
            CommandHandler('sign',    cmd_sign),
            
            CallbackQueryHandler(handle_start_button, pattern=f'^{CB_START_SIGN}$')
        ],
        states={
            WAIT_DOCX: [
                MessageHandler(filters.Document.ALL, receive_docx),
                MessageHandler(
                    filters.PHOTO | filters.VIDEO | filters.AUDIO | filters.VOICE | filters.Sticker.ALL,
                    reject_wrong_type_in_docx,
                ),
            ],
            WAIT_SIGN: [
                MessageHandler(filters.Document.ALL, receive_sign_as_document),
                MessageHandler(filters.PHOTO, receive_sign_as_photo),
                MessageHandler(
                    filters.VIDEO | filters.AUDIO | filters.VOICE | filters.Sticker.ALL,
                    reject_wrong_type_in_sign,
                ),
            ],
            WAIT_KEYWORD: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_keyword),
            ],
            WAIT_ZONE_SELECT: [
                CallbackQueryHandler(handle_zone_select),
            ],
        },
        fallbacks=[
            CommandHandler('cancel',  cmd_cancel),
            CommandHandler('sign',    cmd_sign),
            
        ],
        allow_reentry=True,
    )
    app.add_handler(conv)
    app.add_handler(CallbackQueryHandler(handle_start_button, pattern=f'^{CB_START_SIGN}$'))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, fallback_text))
