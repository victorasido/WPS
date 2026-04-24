import logging
import os

from dotenv import load_dotenv

load_dotenv()

from telegram import Update
from telegram.error import NetworkError, TimedOut
from telegram.ext import Application, ContextTypes

from src.app.handlers.core_handler import setup_core_handlers
from src.app.handlers.document_workflow import setup_workflow_handler
from src.infra.config import (
    TELEGRAM_CONNECT_TIMEOUT,
    TELEGRAM_POOL_TIMEOUT,
    TELEGRAM_READ_TIMEOUT,
    TELEGRAM_WRITE_TIMEOUT,
)

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


async def global_error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Tangkap semua exception yang tidak tertangkap handler lain."""
    error = context.error

    # Telegram network errors: log sebagai WARNING, bukan ERROR — bukan bug kita
    if isinstance(error, (TimedOut, NetworkError)):
        logger.warning("[GlobalErrHandler] Telegram network/timeout error: %s", error)
        return

    # Error lain yang tidak terduga
    logger.error("[GlobalErrHandler] Unhandled exception", exc_info=error)

    # Kalau masih punya akses ke chat, beritahu user
    if isinstance(update, Update) and update.effective_message:
        try:
            await update.effective_message.reply_text(
                "⚠️ Terjadi kesalahan tak terduga. Ketik /cancel lalu /sign untuk memulai ulang."
            )
        except Exception:
            pass  # Jangan sampai error handler sendiri crash


def main():
    token = os.getenv("BOT_TOKEN")
    if not token:
        raise RuntimeError("BOT_TOKEN tidak ditemukan. Isi BOT_TOKEN di file .env.")

    app = (
        Application.builder()
        .token(token)
        .connect_timeout(TELEGRAM_CONNECT_TIMEOUT)
        .read_timeout(TELEGRAM_READ_TIMEOUT)
        .write_timeout(TELEGRAM_WRITE_TIMEOUT)
        .media_write_timeout(TELEGRAM_WRITE_TIMEOUT)
        .pool_timeout(TELEGRAM_POOL_TIMEOUT)
        .build()
    )

    setup_core_handlers(app)
    setup_workflow_handler(app)
    app.add_error_handler(global_error_handler)

    use_webhook = os.getenv("USE_WEBHOOK", "false").lower() == "true"

    if use_webhook:
        webhook_url = os.getenv("WEBHOOK_URL")
        if not webhook_url:
            raise RuntimeError("USE_WEBHOOK=true tapi WEBHOOK_URL tidak diset di .env!")
        webhook_port = int(os.getenv("WEBHOOK_PORT", "8443"))
        webhook_secret = os.getenv("WEBHOOK_SECRET", "")

        logger.info("Word Signer Bot started. Webhook mode: %s (port %d)", webhook_url, webhook_port)
        app.run_webhook(
            listen="0.0.0.0",
            port=webhook_port,
            webhook_url=webhook_url,
            secret_token=webhook_secret or None,
            drop_pending_updates=True,
        )
    else:
        logger.info("Word Signer Bot started. Polling...")
        app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
