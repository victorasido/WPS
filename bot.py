# bot.py — Word Signer Telegram Bot
# Jalankan : python bot.py
# Require  : BOT_TOKEN di .env
#
# Fixes vs versi sebelumnya:
#   - PDF sekarang dikirim via ctx.bot.send_document(chat_id=...) — tidak bergantung
#     pada update.effective_message yang ambiguous di dalam CallbackQueryHandler
#   - msg.delete() dipindah setelah send_document berhasil — tidak lagi block pengiriman
#   - Fitur loop transaksi (WAIT_ACTION, CB_SIGN_AGAIN, CB_EXIT) dihapus
#   - Entry point sekarang pakai inline button, bukan hanya /sign

import os
import io
import logging
import tempfile
from datetime import datetime

from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ConversationHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)

from services.detector_service import detect_signature_zones
from services.converter_service import convert_to_pdf
from services.injector_service import inject_signature
from services.docx_injector_service import inject_signature_to_docx, PlaceholderNotFoundError
from services.logger_service import log_success, log_error

load_dotenv()

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# ── Conversation states ───────────────────────────────────────
WAIT_DOCX, WAIT_SIGN, WAIT_ZONE_SELECT = range(3)

# ── Callback data ─────────────────────────────────────────────
CB_ZONE_TOGGLE  = "zt"
CB_ZONE_ALL     = "za"
CB_ZONE_CONFIRM = "zc"
CB_START_SIGN   = "start_sign"

# ── In-memory storage ─────────────────────────────────────────
user_sessions: dict = {}   # { user_id: session_dict }
user_history:  dict = {}   # { user_id: [history_entry, ...] }
active_users:  set  = set()

MAX_HISTORY = 10


# ── Helpers ───────────────────────────────────────────────────

def _tier_label(conf: float) -> str:
    if conf >= 0.95:   return "exact"
    if conf >= 0.85:   return "case-insensitive"
    return "partial"


def _add_history(user_id: int, docx_name: str, keyword: str,
                 zone_count: int, success: bool):
    entries = user_history.setdefault(user_id, [])
    entries.insert(0, {
        "time":       datetime.now().strftime("%d/%m %H:%M"),
        "docx_name":  docx_name,
        "keyword":    keyword,
        "zone_count": zone_count,
        "success":    success,
    })
    user_history[user_id] = entries[:MAX_HISTORY]


# ── Keyboards ─────────────────────────────────────────────────

def _kb_start() -> InlineKeyboardMarkup:
    """Keyboard di pesan /start."""
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("✍️  Mulai tanda tangan", callback_data=CB_START_SIGN),
    ]])


def _kb_zones(zones: list, selected: set) -> InlineKeyboardMarkup:
    """Keyboard pemilihan zona TTD."""
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


# ── /start ────────────────────────────────────────────────────
async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    name = update.effective_user.first_name or "kamu"
    await update.message.reply_text(
        f"👋 *Halo, {name}! Selamat datang di Word Signer.*\n\n"
        "Aku bisa otomatis sisipkan tanda tangan ke dokumen Word "
        "lalu kirim balik sebagai PDF — langsung dari Telegram.\n\n"
        "Tekan tombol di bawah untuk mulai, atau ketik:\n"
        "• /sign — Mulai proses tanda tangan\n"
        "• /preview — Cek zona TTD tanpa inject\n"
        "• /history — Riwayat transaksi\n"
        "• /help — Panduan lengkap",
        parse_mode="Markdown",
        reply_markup=_kb_start(),
    )


# ── /help ─────────────────────────────────────────────────────
async def cmd_help(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📖 *Panduan Word Signer*\n\n"
        "*Cara pakai:*\n"
        "1. Tekan tombol *Mulai tanda tangan* atau ketik /sign\n"
        "2. Kirim file `.docx`\n"
        "3. Kirim file tanda tangan *(PNG/JPG/SVG)*\n"
        "   Nama file = keyword pencarian di dokumen\n"
        "4. Pilih zona TTD yang ingin di-inject\n"
        "5. Terima PDF ✅\n\n"
        "*Contoh nama file TTD:*\n"
        "• `Nama.png` → cari _Nama_ di dokumen\n"
        "• `Manager Keuangan.png` → cari _Manager Keuangan_\n\n"
        "*Match tier:*\n"
        "• `exact` — cocok persis huruf besar/kecil\n"
        "• `case-insensitive` — cocok tanpa peduli huruf\n"
        "• `partial` — sebagian kata cocok (≥60%)\n\n"
        "/sign · /preview · /history · /cancel",
        parse_mode="Markdown",
        reply_markup=_kb_start(),
    )


# ── /history ──────────────────────────────────────────────────
async def cmd_history(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    history = user_history.get(update.effective_user.id, [])
    if not history:
        await update.message.reply_text(
            "📋 Belum ada riwayat.\n\nTekan tombol di bawah untuk mulai.",
            reply_markup=_kb_start(),
        )
        return

    lines = ["📋 *Riwayat transaksi:*\n"]
    for i, h in enumerate(history, 1):
        icon = "✅" if h["success"] else "❌"
        lines.append(
            f"{i}. {icon} `{h['docx_name'][:30]}` — _{h['time']}_\n"
            f"   🔑 `{h['keyword']}` · {h['zone_count']} zona"
        )

    await update.message.reply_text(
        "\n".join(lines),
        parse_mode="Markdown",
        reply_markup=_kb_start(),
    )


# ── Button handler (entry dari inline button) ─────────────────
async def handle_start_button(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Handle tombol 'Mulai tanda tangan' dari /start atau /help."""
    query = update.callback_query
    await query.answer()
    await query.edit_message_reply_markup(reply_markup=None)  # hapus tombol

    await query.message.reply_text(
        "📄 *Langkah 1 dari 2 — Kirim dokumen Word*\n\n"
        "Kirimkan file `.docx` yang ingin ditandatangani.\n"
        "_(Ketik /cancel untuk membatalkan)_",
        parse_mode="Markdown",
    )
    return WAIT_DOCX


# ── /sign ─────────────────────────────────────────────────────
async def cmd_sign(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id in active_users:
        await update.message.reply_text(
            "⏳ Ada proses yang sedang berjalan. Tunggu sebentar atau /cancel dulu."
        )
        return WAIT_DOCX

    await update.message.reply_text(
        "📄 *Langkah 1 dari 2 — Kirim dokumen Word*\n\n"
        "Kirimkan file `.docx` yang ingin ditandatangani.\n"
        "_(Ketik /cancel untuk membatalkan)_",
        parse_mode="Markdown",
    )
    return WAIT_DOCX


# ── /preview ──────────────────────────────────────────────────
async def cmd_preview(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data["preview_mode"] = True
    await update.message.reply_text(
        "🔍 *Mode Preview — cek zona tanpa inject*\n\n"
        "Kirimkan file `.docx` untuk dicek zona TTD-nya.\n"
        "_(Ketik /cancel untuk membatalkan)_",
        parse_mode="Markdown",
    )
    return WAIT_DOCX


# ── Terima DOCX ───────────────────────────────────────────────
async def receive_docx(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    doc = update.message.document

    if not doc or not doc.file_name.lower().endswith(".docx"):
        await update.message.reply_text(
            "❌ File harus berformat *.docx*. Coba kirim ulang.",
            parse_mode="Markdown",
        )
        return WAIT_DOCX

    msg  = await update.message.reply_text("⏳ Mengunduh dokumen...")
    file = await doc.get_file()
    buf  = io.BytesIO()
    await file.download_to_memory(buf)
    buf.seek(0)

    user_sessions[update.effective_user.id] = {
        "docx_bytes":   buf.read(),
        "docx_name":    doc.file_name,
        "preview_mode": ctx.user_data.pop("preview_mode", False),
        "chat_id":      update.effective_chat.id,
    }

    await msg.edit_text(
        f"✅ *{doc.file_name}* diterima!\n\n"
        "🖊 *Langkah 2 dari 2 — Kirim file tanda tangan*\n\n"
        "Nama file = keyword pencarian di dokumen.\n"
        "• `Nama.png` → cari _Nama_\n"
        "• `Manager Keuangan.png` → cari _Manager Keuangan_\n\n"
        "_(Ketik /cancel untuk membatalkan)_",
        parse_mode="Markdown",
    )
    return WAIT_SIGN


# ── Terima TTD ────────────────────────────────────────────────
async def receive_sign(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    doc     = update.message.document

    if not doc:
        await update.message.reply_text(
            "❌ Kirim sebagai *file/dokumen*, bukan foto.",
            parse_mode="Markdown",
        )
        return WAIT_SIGN

    sign_ext = doc.file_name.rsplit(".", 1)[-1].lower()
    if sign_ext not in ["png", "jpg", "jpeg", "svg"]:
        await update.message.reply_text(
            "❌ Format tanda tangan harus *PNG, JPG, atau SVG*.",
            parse_mode="Markdown",
        )
        return WAIT_SIGN

    session = user_sessions.get(user_id)
    if not session:
        await update.message.reply_text(
            "⚠️ Sesi habis. Ketik /sign untuk mulai ulang."
        )
        return ConversationHandler.END

    msg      = await update.message.reply_text("🔍 Mendeteksi zona TTD...")
    file     = await doc.get_file()
    sign_buf = io.BytesIO()
    await file.download_to_memory(sign_buf)
    sign_buf.seek(0)

    sign_bytes = sign_buf.read()
    keyword    = os.path.splitext(doc.file_name)[0]

    session["sign_bytes"] = sign_bytes
    session["sign_name"]  = doc.file_name

    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            docx_path = os.path.join(tmpdir, session["docx_name"])
            sign_path = os.path.join(tmpdir, doc.file_name)
            with open(docx_path, "wb") as f:
                f.write(session["docx_bytes"])
            with open(sign_path, "wb") as f:
                f.write(sign_bytes)

            # ── STEP 1: TRY TEMPLATE MODE (PRIMARY) ──────────────────
            zones = []
            try:
                await msg.edit_text("📋 [TEMPLATE] Mencari placeholder...")
                modified_docx = inject_signature_to_docx(
                    session["docx_bytes"], sign_path, keyword
                )
                session["template_mode"] = True
                session["modified_docx"] = modified_docx  # sudah ada TTD, tinggal convert
                zones = [{"matched_name": keyword, "confidence": 1.0, "keyword": keyword}]
                logger.info(f"[{user_id}] Template mode detected")

            except PlaceholderNotFoundError:
                # ── FALLBACK: DETECTION MODE ──────────────────────────
                logger.info(f"[{user_id}] No placeholder found, using detection fallback")
                await msg.edit_text("🔍 [FALLBACK] Mencari zona TTD...")
                zones = detect_signature_zones(
                    docx_path, sign_path, confidence_threshold=0.4
                )
                session["template_mode"] = False

        if not zones:
            _add_history(user_id, session["docx_name"], keyword, 0, False)
            await msg.edit_text(
                f"❌ *Keyword tidak ditemukan di dokumen.*\n\n"
                f"Keyword yang dicari: `{keyword}`\n\n"
                "Pastikan nama file TTD mengandung kata/frasa yang ada di dokumen.\n\n"
                "Ketik /sign untuk mencoba lagi.",
                parse_mode="Markdown",
            )
            user_sessions.pop(user_id, None)
            return ConversationHandler.END

        # Preview mode → tampilkan zona dan selesai
        if session.get("preview_mode"):
            lines = [f"🔍 *Preview zona TTD — keyword: `{keyword}`*\n\nDitemukan {len(zones)} zona:\n"]
            for i, z in enumerate(zones, 1):
                name = (z.get("matched_name") or z.get("keyword") or f"Zona {i}")[:50]
                pos  = z.get("inject_position", "")
                lines.append(
                    f"{i}. `{name}`\n"
                    f"   {z['confidence']:.0%} · {_tier_label(z['confidence'])} · {pos}"
                )
            lines.append("\n_Gunakan /sign untuk inject tanda tangan._")
            await msg.edit_text("\n".join(lines), parse_mode="Markdown")
            user_sessions.pop(user_id, None)
            return ConversationHandler.END

        session["zones"]    = zones
        session["selected"] = set(range(len(zones)))

        # ── TEMPLATE MODE: skip zone selection, langsung konfirmasi ──
        if session.get("template_mode"):
            await msg.edit_text(
                f"✅ *[TEMPLATE]* Placeholder ditemukan!\n\n"
                "Tekan tombol di bawah untuk proses.",
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("✍️  Proses", callback_data=CB_ZONE_CONFIRM)
                ]]),
            )
            return WAIT_ZONE_SELECT

        # ── FALLBACK MODE: zone selection dialog normal ──
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
        user_sessions.pop(user_id, None)
        return ConversationHandler.END


# ── Zone selection ────────────────────────────────────────────
async def handle_zone_select(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query   = update.callback_query
    user_id = update.effective_user.id
    await query.answer()

    session = user_sessions.get(user_id)
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

        # Hapus keyboard → tampilkan status proses
        await query.edit_message_text(
            f"⚙️ Memproses {len(selected)} zona... mohon tunggu.",
        )
        return await _process_document(update, ctx, query.message)


# ── Core processing ───────────────────────────────────────────
async def _process_document(update: Update, ctx: ContextTypes.DEFAULT_TYPE, status_msg):
    """Convert DOCX → inject TTD → kirim PDF ke user."""
    user_id = update.effective_user.id
    session = user_sessions.get(user_id)
    if not session:
        return ConversationHandler.END

    active_users.add(user_id)

    docx_name      = session["docx_name"]
    sign_name      = session["sign_name"]
    sign_bytes     = session["sign_bytes"]
    zones          = session["zones"]
    selected       = session["selected"]
    selected_zones = [zones[i] for i in sorted(selected)]
    keyword        = os.path.splitext(sign_name)[0]
    chat_id        = session["chat_id"]
    is_template    = session.get("template_mode", False)
    success        = False

    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            sign_path = os.path.join(tmpdir, sign_name)
            with open(sign_path, "wb") as f:
                f.write(sign_bytes)

            if is_template:
                # ── TEMPLATE PATH: modified_docx sudah ada TTD → tinggal convert ──
                await status_msg.edit_text("📋 [TEMPLATE] Mengkonversi DOCX ke PDF...")
                modified_docx = session["modified_docx"]
                signed_pdf = convert_to_pdf(modified_docx)
                logger.info(f"[{user_id}] Template path: converted modified DOCX to PDF")
            else:
                # ── FALLBACK PATH: original docx → PDF → inject TTD ──
                docx_bytes = session["docx_bytes"]

                await status_msg.edit_text("📄 Mengkonversi dokumen ke PDF...")
                pdf_bytes = convert_to_pdf(docx_bytes)

                await status_msg.edit_text(
                    f"✍️ Menyisipkan tanda tangan di {len(selected_zones)} zona..."
                )
                signed_pdf = inject_signature(pdf_bytes, sign_path, selected_zones)
                logger.info(f"[{user_id}] Fallback path: injected {len(selected_zones)} zones")

        # ── Kirim PDF ───────────────────────────────────────────
        output_name = docx_name.replace(".docx", "_signed.pdf")
        mode_label  = "📋 Template" if is_template else f"🔍 Fallback ({len(selected_zones)} zona)"

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
                f"📋 `{docx_name}`\n"
                f"🔑 Keyword: `{keyword}`\n"
                f"✍️ Tanda tangan:\n{zone_summary}\n\n"
                f"📎 `{output_name}`\n\n"
                f"_Ketik /sign untuk dokumen berikutnya._"
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
        log_success(docx_name, "telegram_output", n_zones)
        success = True

    except Exception as e:
        logger.exception("Error saat proses dokumen")
        log_error(docx_name, str(e))
        try:
            await status_msg.edit_text(
                f"❌ *Gagal memproses dokumen:*\n`{e}`\n\n"
                "Ketik /sign untuk mencoba lagi.",
                parse_mode="Markdown",
            )
        except Exception:
            pass

    finally:
        active_users.discard(user_id)
        n_zones = 1 if is_template else len(selected_zones)
        _add_history(user_id, docx_name, keyword, n_zones, success)
        user_sessions.pop(user_id, None)

    return ConversationHandler.END


# ── /cancel ───────────────────────────────────────────────────
async def cmd_cancel(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_sessions.pop(user_id, None)
    active_users.discard(user_id)
    ctx.user_data.clear()
    await update.message.reply_text(
        "🚫 Proses dibatalkan.\n\nTekan tombol di bawah atau ketik /sign untuk mulai lagi.",
        reply_markup=_kb_start(),
    )
    return ConversationHandler.END


# ── Fallback ──────────────────────────────────────────────────
async def fallback_text(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Tekan tombol di bawah atau ketik /sign untuk mulai.",
        reply_markup=_kb_start(),
    )


# ── Main ──────────────────────────────────────────────────────
def main():
    token = os.getenv("BOT_TOKEN")
    if not token:
        raise RuntimeError(
            "BOT_TOKEN tidak ditemukan. Isi BOT_TOKEN di file .env."
        )

    app = Application.builder().token(token).build()

    conv = ConversationHandler(
        entry_points=[
            CommandHandler("sign",    cmd_sign),
            CommandHandler("preview", cmd_preview),
            CallbackQueryHandler(handle_start_button, pattern=f"^{CB_START_SIGN}$"),
        ],
        states={
            WAIT_DOCX: [
                MessageHandler(filters.Document.ALL, receive_docx),
            ],
            WAIT_SIGN: [
                MessageHandler(filters.Document.ALL, receive_sign),
            ],
            WAIT_ZONE_SELECT: [
                CallbackQueryHandler(handle_zone_select),
            ],
        },
        fallbacks=[
            CommandHandler("cancel", cmd_cancel),
            CommandHandler("sign",   cmd_sign),
            CommandHandler("start",  cmd_start),
            CommandHandler("help",   cmd_help),
            CommandHandler("history", cmd_history),
        ],
        allow_reentry=True,
    )

    # Add handlers di luar conversation agar universally accessible
    app.add_handler(CommandHandler("start",   cmd_start))
    app.add_handler(CommandHandler("help",    cmd_help))
    app.add_handler(CommandHandler("history", cmd_history))
    app.add_handler(conv)
    app.add_handler(
        CallbackQueryHandler(handle_start_button, pattern=f"^{CB_START_SIGN}$")
    )
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, fallback_text))

    logger.info("🤖 Word Signer Bot started. Polling...")
    app.run_polling()


if __name__ == "__main__":
    main()