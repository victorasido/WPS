from telegram import Update
from telegram.ext import (
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

from src.app.handlers.docx_handler import WAIT_ZONE_SELECT, handle_zone_select, run_docx_detect
from src.app.handlers.pdf_handler import WAIT_KEYWORD, after_sign_received as after_pdf_sign, receive_keyword
from src.app.ui import messages
from src.app.ui.keyboards import CB_START_SIGN, get_start_keyboard
from src.app.utils.tg_downloader import download_tg_file
from src.infra.database import session_manager
from src.infra.config import (
    TELEGRAM_CONNECT_TIMEOUT,
    TELEGRAM_POOL_TIMEOUT,
    TELEGRAM_READ_TIMEOUT,
    TELEGRAM_WRITE_TIMEOUT,
)
from src.shared.validators import validate_document_file, validate_signature_file

WAIT_DOCX = 0
WAIT_SIGN = 1


async def handle_start_button(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_reply_markup(reply_markup=None)
    await query.message.reply_text(messages.get_step_1_send_document(), parse_mode="Markdown")
    return WAIT_DOCX


async def cmd_sign(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if session_manager.is_active(update.effective_user.id):
        await update.message.reply_text(messages.get_active_process_warning())
        return WAIT_DOCX
    await update.message.reply_text(messages.get_step_1_send_document(), parse_mode="Markdown")
    return WAIT_DOCX


async def receive_document(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    doc = msg.document
    if not doc:
        await msg.reply_text(messages.get_invalid_document_message(), parse_mode="Markdown")
        return WAIT_DOCX

    is_valid, error = validate_document_file(doc.file_name, doc.file_size)
    if not is_valid:
        await msg.reply_text(error, parse_mode="Markdown")
        return WAIT_DOCX

    is_docx = (doc.file_name or "").lower().endswith(".docx")
    status_msg = await msg.reply_text(
        messages.get_downloading_document(),
        connect_timeout=TELEGRAM_CONNECT_TIMEOUT,
        read_timeout=TELEGRAM_READ_TIMEOUT,
        write_timeout=TELEGRAM_WRITE_TIMEOUT,
        pool_timeout=TELEGRAM_POOL_TIMEOUT,
    )
    session_manager.set_document(
        user_id=update.effective_user.id,
        doc_bytes=await download_tg_file(msg),
        doc_name=doc.file_name,
        doc_type="docx" if is_docx else "pdf",
        chat_id=update.effective_chat.id,
    )
    await status_msg.edit_text(
        messages.get_document_received(doc.file_name, is_docx),
        parse_mode="Markdown",
        connect_timeout=TELEGRAM_CONNECT_TIMEOUT,
        read_timeout=TELEGRAM_READ_TIMEOUT,
        write_timeout=TELEGRAM_WRITE_TIMEOUT,
        pool_timeout=TELEGRAM_POOL_TIMEOUT,
    )
    return WAIT_SIGN


async def reject_wrong_type_in_docx(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    kind = "photo" if msg.photo else "video" if msg.video else "audio" if msg.audio or msg.voice else "sticker" if msg.sticker else "unknown"
    await msg.reply_text(messages.get_wait_docx_wrong_type(kind), parse_mode="Markdown")
    return WAIT_DOCX


async def receive_sign_as_document(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    doc = msg.document
    mime = (doc.mime_type or "") if doc else ""
    is_valid, error = validate_signature_file(doc.file_name, mime)
    if not is_valid:
        await msg.reply_text(error, parse_mode="Markdown")
        return WAIT_SIGN
    return await _store_signature_and_route(update, ctx, sign_bytes=await download_tg_file(msg), sign_name=doc.file_name or "signature.png")


async def receive_sign_as_photo(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    session = session_manager.get_session(update.effective_user.id, include_blobs=False)
    if not session:
        await update.message.reply_text(messages.get_session_expired())
        return ConversationHandler.END

    await update.message.reply_text(
        messages.get_photo_signature_received(),
        parse_mode="Markdown",
        connect_timeout=TELEGRAM_CONNECT_TIMEOUT,
        read_timeout=TELEGRAM_READ_TIMEOUT,
        write_timeout=TELEGRAM_WRITE_TIMEOUT,
        pool_timeout=TELEGRAM_POOL_TIMEOUT,
    )
    return await _store_signature_and_route(update, ctx, sign_bytes=await download_tg_file(update.message), sign_name="signature.jpg")


async def _store_signature_and_route(
    update: Update,
    ctx: ContextTypes.DEFAULT_TYPE,
    *,
    sign_bytes: bytes,
    sign_name: str,
):
    user_id = update.effective_user.id
    session = session_manager.get_session(user_id, include_blobs=False)
    if not session:
        await update.message.reply_text(messages.get_session_expired())
        return ConversationHandler.END

    session_manager.update_session(user_id, sign_bytes=sign_bytes, sign_name=sign_name)
    return await (run_docx_detect(update, ctx) if session["doc_type"] == "docx" else after_pdf_sign(update, ctx))


async def reject_wrong_type_in_sign(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    if msg.video:
        kind = "video"
    elif msg.audio or msg.voice:
        kind = "audio"
    elif msg.sticker:
        kind = "sticker"
    elif msg.document:
        ext = (msg.document.file_name or "").rsplit(".", 1)[-1].lower()
        kind = "document_again" if ext in ["docx", "pdf", "doc"] else "unsupported_document"
    else:
        kind = "unknown"
    await msg.reply_text(messages.get_wait_sign_wrong_type(kind), parse_mode="Markdown")
    return WAIT_SIGN


async def cmd_cancel(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    session_manager.clear_session(user_id)
    session_manager.remove_active_user(user_id)
    ctx.user_data.clear()
    await update.message.reply_text(messages.get_cancelled(), reply_markup=get_start_keyboard())
    return ConversationHandler.END


async def fallback_text(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(messages.get_fallback_text(), reply_markup=get_start_keyboard())


def setup_workflow_handler(app):
    conv = ConversationHandler(
        entry_points=[CommandHandler("sign", cmd_sign), CallbackQueryHandler(handle_start_button, pattern=f"^{CB_START_SIGN}$")],
        states={
            WAIT_DOCX: [
                MessageHandler(filters.Document.ALL, receive_document),
                MessageHandler(filters.PHOTO | filters.VIDEO | filters.AUDIO | filters.VOICE | filters.Sticker.ALL, reject_wrong_type_in_docx),
            ],
            WAIT_SIGN: [
                MessageHandler(filters.Document.ALL, receive_sign_as_document),
                MessageHandler(filters.PHOTO, receive_sign_as_photo),
                MessageHandler(filters.VIDEO | filters.AUDIO | filters.VOICE | filters.Sticker.ALL, reject_wrong_type_in_sign),
            ],
            WAIT_KEYWORD: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_keyword)],
            WAIT_ZONE_SELECT: [CallbackQueryHandler(handle_zone_select)],
        },
        fallbacks=[CommandHandler("cancel", cmd_cancel), CommandHandler("sign", cmd_sign)],
        allow_reentry=True,
    )
    app.add_handler(conv)
    app.add_handler(CallbackQueryHandler(handle_start_button, pattern=f"^{CB_START_SIGN}$"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, fallback_text))
