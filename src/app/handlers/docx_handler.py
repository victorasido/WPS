import io
import os

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes, ConversationHandler

from src.app.services.workflow_orchestrator import WorkflowOrchestrator
from src.app.ui import messages
from src.app.ui.keyboards import (
    CB_ZONE_ALL,
    CB_ZONE_CONFIRM,
    CB_ZONE_TOGGLE,
    get_zone_selection_keyboard,
)
from src.app.utils.decorators import handle_workflow_error
from src.infra.database import LogRepository, session_manager
from src.infra.config import (
    TELEGRAM_CONNECT_TIMEOUT,
    TELEGRAM_POOL_TIMEOUT,
    TELEGRAM_READ_TIMEOUT,
    TELEGRAM_WRITE_TIMEOUT,
)

log_repo = LogRepository()

WAIT_ZONE_SELECT = 2


async def run_docx_detect(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    session = session_manager.get_session(user_id, include_blobs=False)
    if not session:
        await update.message.reply_text(messages.get_session_expired())
        return ConversationHandler.END

    status_msg = await update.message.reply_text(messages.get_detecting_zones())
    return await _detect_docx_zones(update, ctx, status_msg)


@handle_workflow_error(
    process_name="DOCX detect",
    error_message_factory=messages.get_detect_zones_failed,
    clear_session=True,
)
async def _detect_docx_zones(
    update: Update,
    ctx: ContextTypes.DEFAULT_TYPE,
    status_msg,
):
    user_id = update.effective_user.id
    session = session_manager.get_session(user_id)
    if not session:
        await update.message.reply_text(messages.get_session_expired())
        return ConversationHandler.END

    await status_msg.edit_text(messages.get_processing_document())
    result = await WorkflowOrchestrator.detect_docx_zones(
        session["doc_bytes"],
        session["sign_bytes"],
        session["doc_name"],
        session["sign_name"],
    )

    keyword = result["keyword"]
    zones = result["zones"]
    session["template_mode"] = result["is_template"]
    session["modified_docx"] = result["modified_docx"]

    session_manager.update_session(
        user_id,
        keyword=keyword,
        zones=zones,
        selected=list(range(len(zones))),
        template_mode=session.get("template_mode", False),
        modified_docx=session.get("modified_docx"),
    )
    session = session_manager.get_session(user_id, include_blobs=False)

    if not zones:
        await status_msg.edit_text(
            messages.get_docx_keyword_not_found(keyword),
            parse_mode="Markdown",
        )
        session_manager.clear_session(user_id)
        return ConversationHandler.END

    if session.get("template_mode"):
        await status_msg.edit_text(
            messages.get_template_placeholder_found(),
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton(
                    messages.TEMPLATE_PROCESS_BUTTON,
                    callback_data=CB_ZONE_CONFIRM,
                )
            ]]),
        )
        return WAIT_ZONE_SELECT

    await status_msg.edit_text(
        messages.get_zone_selection_found(len(zones), keyword),
        parse_mode="Markdown",
        reply_markup=get_zone_selection_keyboard(zones, session["selected"]),
    )
    return WAIT_ZONE_SELECT


async def handle_zone_select(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = update.effective_user.id
    await query.answer()

    session = session_manager.get_session(user_id, include_blobs=False)
    if not session:
        await query.edit_message_text(messages.get_session_expired())
        return ConversationHandler.END

    zones = session["zones"]
    selected = set(session["selected"])
    data = query.data

    if data.startswith(f"{CB_ZONE_TOGGLE}:"):
        idx = int(data.split(":")[1])
        selected.discard(idx) if idx in selected else selected.add(idx)
        session_manager.update_session(user_id, selected=list(selected))
        await query.edit_message_reply_markup(
            reply_markup=get_zone_selection_keyboard(zones, selected)
        )
        return WAIT_ZONE_SELECT

    if data == CB_ZONE_ALL:
        if len(selected) == len(zones):
            selected.clear()
        else:
            selected.update(range(len(zones)))

        session_manager.update_session(user_id, selected=list(selected))
        await query.edit_message_reply_markup(
            reply_markup=get_zone_selection_keyboard(zones, selected)
        )
        return WAIT_ZONE_SELECT

    if data == CB_ZONE_CONFIRM:
        if not selected:
            await query.answer(messages.get_select_min_zone_alert(), show_alert=True)
            return WAIT_ZONE_SELECT

        await query.edit_message_text(messages.get_processing_zones(len(selected)))
        return await _process_docx(update, ctx, query.message)


@handle_workflow_error(
    process_name="DOCX process",
    error_message_factory=messages.get_docx_processing_failed,
)
async def _process_docx(
    update: Update,
    ctx: ContextTypes.DEFAULT_TYPE,
    status_msg,
):
    """Convert DOCX -> inject TTD -> kirim PDF ke user."""
    user_id = update.effective_user.id
    session = session_manager.get_session(user_id)
    if not session:
        return ConversationHandler.END

    session_manager.add_active_user(user_id)

    doc_name = session["doc_name"]
    sign_name = session["sign_name"]
    sign_bytes = session["sign_bytes"]
    zones = session["zones"]
    selected = session["selected"]
    selected_zones = [zones[i] for i in sorted(selected)]
    keyword = session.get("keyword", os.path.splitext(sign_name)[0])
    chat_id = session["chat_id"]
    is_template = session.get("template_mode", False)

    try:
        await status_msg.edit_text(
            messages.get_docx_processing_status(len(selected_zones), is_template)
        )

        async def _notify_queued():
            await status_msg.edit_text(messages.get_conversion_queued(), parse_mode="Markdown")

        signed_pdf = await WorkflowOrchestrator.process_docx_injection(
            doc_bytes=session["doc_bytes"],
            sign_bytes=sign_bytes,
            sign_name=sign_name,
            selected_zones=selected_zones,
            is_template=is_template,
            modified_docx=session.get("modified_docx"),
            on_queued=_notify_queued,
        )

        output_name = doc_name.replace(".docx", "_signed.pdf")

        await ctx.bot.send_document(
            chat_id=chat_id,
            document=io.BytesIO(signed_pdf),
            filename=output_name,
            caption=messages.get_success_docx(
                doc_name=doc_name,
                keyword=keyword,
                output_name=output_name,
                selected_zones=selected_zones,
                is_template=is_template,
            ),
            parse_mode="Markdown",
            read_timeout=TELEGRAM_READ_TIMEOUT,
            write_timeout=TELEGRAM_WRITE_TIMEOUT,
            connect_timeout=TELEGRAM_CONNECT_TIMEOUT,
            pool_timeout=TELEGRAM_POOL_TIMEOUT,
        )

        try:
            await status_msg.delete()
        except Exception:
            pass

        n_zones = 1 if is_template else len(selected_zones)
        log_repo.log_success(doc_name, "telegram_output", n_zones)
    finally:
        session_manager.remove_active_user(user_id)
        session_manager.clear_session(user_id)

    return ConversationHandler.END
