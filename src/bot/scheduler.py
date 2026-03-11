"""Ütemezett feladatok - napi automatikus elemzés és küldés.

python-telegram-bot beépített JobQueue-t használ (APScheduler alapú).
"""

import logging
from datetime import time
from zoneinfo import ZoneInfo

from telegram.ext import Application

from src.bot.formatter import format_daily_report, split_message
from src.config import TELEGRAM_CHAT_ID
from src.pipeline import run_prediction_pipeline

logger = logging.getLogger(__name__)

CET = ZoneInfo("Europe/Budapest")


async def daily_report_job(context) -> None:
    """Napi automatikus elemzés és küldés."""
    chat_id = TELEGRAM_CHAT_ID
    if not chat_id:
        logger.error("TELEGRAM_CHAT_ID nincs beállítva, napi report kihagyva.")
        return

    logger.info("Napi automatikus elemzés indítása...")

    try:
        result = run_prediction_pipeline()

        report = format_daily_report(result)
        parts = split_message(report)

        for part in parts:
            await context.bot.send_message(
                chat_id=chat_id,
                text=part,
                parse_mode="MarkdownV2",
            )

        logger.info(
            "Napi report elküldve: %d meccs, %d predikció",
            result.total_matches, len(result.predictions),
        )

    except Exception as e:
        logger.error("Napi report hiba: %s", e, exc_info=True)
        try:
            await context.bot.send_message(
                chat_id=chat_id,
                text=f"Hiba a napi elemzés során: {e}",
            )
        except Exception:
            pass


def setup_scheduler(app: Application) -> None:
    """Ütemezett feladatok regisztrálása."""
    job_queue = app.job_queue

    # Napi 10:00 CET
    job_queue.run_daily(
        daily_report_job,
        time=time(hour=10, minute=0, tzinfo=CET),
        name="daily_report",
    )

    logger.info("Napi report ütemezve: 10:00 CET")
