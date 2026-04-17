import io

from telegram import Update
from telegram.constants import ChatAction
from telegram.ext import ContextTypes, ConversationHandler

from src.app.services.workflow_orchestrator import WorkflowOrchestrator
from src.app.ui import messages
from src.app.utils.decorators import handle_workflow_error
from src.infra.database import LogRepository, session_manager
from src.shared.text_utils import extract_keyword
from src.shared.validators import validate_keyword

log_repo = LogRepository()

WAIT_KEYWORD = 3


async def after_sign_received(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    session = session_manager.get_session(user_id)
    if not session:
        await update.message.reply_text(messages.get_session_expired())
        return ConversationHandler.END

    keyword = extract_keyword(session.get("sign_name", "signature.png"))
    sign_name = session.get("sign_name", "signature.png")

    session_manager.update_session(
        user_id,
        keyword=keyword,
        sign_name=sign_name,
    )

    status_msg = await update.message.reply_text(
        messages.get_pdf_received_searching(keyword),
        parse_mode="Markdown",
    )
    await update.message._bot.send_chat_action(
        chat_id=update.effective_chat.id,
        action=ChatAction.UPLOAD_DOCUMENT,
    )
    return await _run_pdf_bypass(update, ctx, status_msg)


async def receive_keyword(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Terima keyword dari user untuk PDF bypass."""
    msg = update.message
    keyword = (msg.text or "").strip()

    is_valid, error = validate_keyword(keyword)
    if not is_valid:
        await msg.reply_text(error, parse_mode="Markdown")
        return WAIT_KEYWORD

    user_id = update.effective_user.id
    session = session_manager.get_session(user_id)
    if not session:
        await msg.reply_text(messages.get_session_expired())
        return ConversationHandler.END

    session_manager.update_session(
        user_id,
        keyword=keyword,
        sign_name=session.get("sign_name", "signature.png"),
    )

    status_msg = await msg.reply_text(
        messages.get_pdf_keyword_searching(keyword),
        parse_mode="Markdown",
    )
    await ctx.bot.send_chat_action(
        chat_id=update.effective_chat.id,
        action=ChatAction.UPLOAD_DOCUMENT,
    )

    return await _run_pdf_bypass(update, ctx, status_msg)


@handle_workflow_error(
    process_name="PDF bypass",
    error_message_factory=messages.get_pdf_processing_failed,
)
async def _run_pdf_bypass(
    update: Update,
    ctx: ContextTypes.DEFAULT_TYPE,
    status_msg,
):
    """
    PDF bypass: skip detector & LibreOffice.
    Scan hanya page 0 + 2 halaman terakhir.
    """
    user_id = update.effective_user.id
    session = session_manager.get_session(user_id)
    if not session:
        return ConversationHandler.END

    keyword = session["keyword"]
    doc_name = session["doc_name"]
    chat_id = session["chat_id"]

    session_manager.add_active_user(user_id)
    try:
        await status_msg.edit_text(messages.get_processing_pdf())
        signed_pdf = await WorkflowOrchestrator.process_pdf_bypass(
            session["doc_bytes"],
            session["sign_bytes"],
            session["sign_name"],
            keyword,
            [],
        )

        output_name = doc_name.replace(".pdf", "_signed.pdf")
        if not output_name.endswith(".pdf"):
            output_name += "_signed.pdf"

        await ctx.bot.send_document(
            chat_id=chat_id,
            document=io.BytesIO(signed_pdf),
            filename=output_name,
            caption=messages.get_success_pdf(doc_name, keyword, output_name),
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
    except ValueError:
        await status_msg.edit_text(
            messages.get_pdf_keyword_not_found(keyword),
            parse_mode="Markdown",
        )
        return ConversationHandler.END
    finally:
        session_manager.remove_active_user(user_id)
        session_manager.clear_session(user_id)

    return ConversationHandler.END
