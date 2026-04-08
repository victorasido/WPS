from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ContextTypes, CommandHandler, CallbackQueryHandler

# Shared constants that might be needed
CB_START_SIGN = "start_sign"

def _kb_start() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("✍️  Mulai tanda tangan", callback_data=CB_START_SIGN),
    ]])


async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    name = update.effective_user.first_name or "kamu"
    await update.message.reply_text(
        f"👋 *Halo, {name}! Selamat datang di Word Signer.*\n\n"
        "Aku bisa otomatis sisipkan tanda tangan ke dokumen Word atau PDF "
        "lalu kirim balik sebagai PDF — langsung dari Telegram.\n\n"
        "Tekan tombol di bawah untuk mulai, atau ketik:\n"
        "• /sign — Mulai proses tanda tangan\n"
        "• /help — Panduan lengkap",
        parse_mode="Markdown",
        reply_markup=_kb_start(),
    )


async def cmd_help(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📖 *Panduan Word Signer*\n\n"
        "*Cara pakai (DOCX):*\n"
        "1. Ketik /sign\n"
        "2. Kirim file `.docx`\n"
        "3. Kirim file tanda tangan *(PNG/JPG/SVG)*\n"
        "   Nama file = keyword pencarian di dokumen\n"
        "4. Pilih zona TTD → terima PDF ✅\n\n"
        "*Cara pakai (PDF):*\n"
        "1. Ketik /sign\n"
        "2. Kirim file `.pdf`\n"
        "3. Kirim file tanda tangan\n"
        "4. Ketik nama/jabatan target → terima PDF ✅\n\n"
        "*Tips TTD:*\n"
        "• Kirim TTD sebagai *File* (bukan Photo) agar tidak blur\n"
        "• Nama file = keyword: `Manager Keuangan.png`\n\n"
        "/sign · /cancel",
        parse_mode="Markdown",
        reply_markup=_kb_start(),
    )


def setup_core_handlers(app):
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_help))
