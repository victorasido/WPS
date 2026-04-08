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

    logger.info("🤖 Word Signer Bot started. Polling...")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()