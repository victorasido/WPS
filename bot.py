# bot.py — Word Signer Telegram Bot
# Refactored Entry Point

import os
import logging
from dotenv import load_dotenv
from telegram.ext import Application
from src.app.handlers.core_handler import setup_core_handlers
from src.app.handlers.document_workflow import setup_workflow_handler

load_dotenv()

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

def main():
    token = os.getenv("BOT_TOKEN")
    if not token:
        raise RuntimeError("BOT_TOKEN tidak ditemukan. Isi BOT_TOKEN di file .env.")

    app = Application.builder().token(token).build()

    # Register handlers from separate modules
    setup_core_handlers(app)
    setup_workflow_handler(app)

    use_webhook = os.getenv("USE_WEBHOOK", "false").lower() == "true"

    if use_webhook:
        webhook_url = os.getenv("WEBHOOK_URL")
        if not webhook_url:
            raise RuntimeError("USE_WEBHOOK=true tapi WEBHOOK_URL tidak diset di .env!")
        webhook_port = int(os.getenv("WEBHOOK_PORT", "8443"))
        webhook_secret = os.getenv("WEBHOOK_SECRET", "")

        logger.info("🌐 Word Signer Bot started. Webhook mode: %s (port %d)", webhook_url, webhook_port)
        app.run_webhook(
            listen="0.0.0.0",
            port=webhook_port,
            webhook_url=webhook_url,
            secret_token=webhook_secret or None,
            drop_pending_updates=True,
        )
    else:
        logger.info("🤖 Word Signer Bot started. Polling...")
        app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()