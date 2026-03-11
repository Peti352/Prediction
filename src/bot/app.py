"""Telegram bot belépési pont.

Futtatás:
    python -m src.bot.app

Szükséges environment változók:
    TELEGRAM_BOT_TOKEN - BotFather-től kapott token
    TELEGRAM_CHAT_ID   - Chat/csoport ID a napi reporthoz
"""

import logging
import sys
from pathlib import Path

# Projekt root hozzáadása a path-hoz
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from telegram.ext import ApplicationBuilder, CommandHandler

from src.bot.handlers import (
    help_handler,
    league_handler,
    start_handler,
    tips_handler,
    today_handler,
    value_handler,
)
from src.bot.scheduler import setup_scheduler
from src.config import SUPPORTED_LEAGUES, TELEGRAM_BOT_TOKEN

# Logging beállítás
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


def create_bot_application():
    """Bot Application létrehozása és konfigurálása."""
    if not TELEGRAM_BOT_TOKEN:
        logger.error(
            "TELEGRAM_BOT_TOKEN nincs beállítva!\n"
            "  1. Beszélj a @BotFather-rel a Telegramon\n"
            "  2. /newbot paranccsal hozz létre egy botot\n"
            "  3. TELEGRAM_BOT_TOKEN=<token> a .env fájlba"
        )
        sys.exit(1)

    app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()

    # Alap parancsok
    app.add_handler(CommandHandler("start", start_handler))
    app.add_handler(CommandHandler("help", help_handler))
    app.add_handler(CommandHandler("today", today_handler))
    app.add_handler(CommandHandler("tips", tips_handler))
    app.add_handler(CommandHandler("value", value_handler))

    # Liga-specifikus parancsok
    for code in SUPPORTED_LEAGUES:
        app.add_handler(CommandHandler(code.lower(), league_handler))

    # Ütemezett feladatok
    setup_scheduler(app)

    return app


def main():
    """Bot indítása polling módban."""
    logger.info("TipMix Prediction Bot indítása...")
    app = create_bot_application()
    logger.info("Bot elindult! Polling mód aktív.")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
