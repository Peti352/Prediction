"""Telegram bot parancskezelők.

Parancsok:
    /start - Üdvözlés
    /help  - Parancsok listája
    /today - Napi teljes elemzés
    /tips  - Szelvényjavaslatok
    /value - Csak value betek
    /pl, /bl1, /sa, /pd, /fl1 - Liga-specifikus elemzés
"""

import logging

from telegram import Update
from telegram.ext import ContextTypes

from src.bot.formatter import (
    escape_md,
    format_daily_report,
    format_league_report,
    format_tickets,
    format_value_bets,
    split_message,
)
from src.config import SUPPORTED_LEAGUES
from src.pipeline import PipelineResult, run_prediction_pipeline

logger = logging.getLogger(__name__)

# Cache az utolsó pipeline eredményhez (6 órás cache a pipeline-ban is van)
_last_result: PipelineResult | None = None


async def _get_result(competition: str | None = None) -> PipelineResult:
    """Pipeline futtatás cache-eléssel."""
    global _last_result

    # Ha liga-specifikus kérés, mindig új pipeline
    if competition:
        return run_prediction_pipeline(competition=competition)

    # Cache: ha van friss eredmény (< 1 óra), használjuk
    if _last_result and _last_result.predictions:
        from datetime import datetime, timedelta
        if datetime.now() - _last_result.timestamp < timedelta(hours=1):
            return _last_result

    _last_result = run_prediction_pipeline()
    return _last_result


async def _send_long_message(
    update: Update, text: str, parse_mode: str = "MarkdownV2"
) -> None:
    """Hosszú üzenet küldés darabolással."""
    parts = split_message(text)
    for part in parts:
        try:
            await update.message.reply_text(part, parse_mode=parse_mode)
        except Exception as e:
            logger.warning("MarkdownV2 hiba, plaintext fallback: %s", e)
            # Fallback: plain text
            clean = part.replace("\\", "").replace("*", "").replace("_", "")
            await update.message.reply_text(clean)


async def start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/start parancs."""
    text = (
        "*TipMix Prediction Bot* 🤖⚽\n\n"
        "Üdv\\! Ez a bot napi focimeccs elemzéseket küld "
        "Poisson\\-modell és statisztikai O/U analízis alapján\\.\n\n"
        "Használd a /help parancsot a lehetőségekhez\\."
    )
    await update.message.reply_text(text, parse_mode="MarkdownV2")


async def help_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/help parancs."""
    leagues = "\n".join(
        f"  /{code.lower()} \\- {escape_md(info['name'])}"
        for code, info in SUPPORTED_LEAGUES.items()
    )

    text = (
        "*Elérhető parancsok:*\n\n"
        "/today \\- Napi teljes elemzés\n"
        "/tips \\- Szelvényjavaslatok\n"
        "/value \\- Value bet lehetőségek\n\n"
        "*Liga\\-specifikus:*\n"
        f"{leagues}\n\n"
        "_Az elemzés néhány percet vehet igénybe\\._"
    )
    await update.message.reply_text(text, parse_mode="MarkdownV2")


async def today_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/today parancs - napi teljes elemzés."""
    await update.message.reply_text("Elemzés folyamatban... ⏳")

    try:
        result = await _get_result()
        report = format_daily_report(result)
        await _send_long_message(update, report)
    except Exception as e:
        logger.error("/today hiba: %s", e, exc_info=True)
        await update.message.reply_text(f"Hiba az elemzés során: {e}")


async def tips_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/tips parancs - szelvényjavaslatok."""
    await update.message.reply_text("Szelvények generálása... ⏳")

    try:
        result = await _get_result()
        report = format_tickets(result.tickets)
        await _send_long_message(update, report)
    except Exception as e:
        logger.error("/tips hiba: %s", e, exc_info=True)
        await update.message.reply_text(f"Hiba: {e}")


async def value_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/value parancs - csak value betek."""
    await update.message.reply_text("Value betek keresése... ⏳")

    try:
        result = await _get_result()
        report = format_value_bets(result)
        await _send_long_message(update, report)
    except Exception as e:
        logger.error("/value hiba: %s", e, exc_info=True)
        await update.message.reply_text(f"Hiba: {e}")


async def league_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Liga-specifikus elemzés handler (/pl, /bl1, /sa, /pd, /fl1)."""
    # Parancs nevéből kiolvassuk a liga kódot
    command = update.message.text.strip("/").split("@")[0].upper()

    if command not in SUPPORTED_LEAGUES:
        await update.message.reply_text(
            f"Ismeretlen liga: {command}\n"
            f"Elérhető: {', '.join(SUPPORTED_LEAGUES.keys())}"
        )
        return

    league_name = SUPPORTED_LEAGUES[command]["name"]
    await update.message.reply_text(f"{league_name} elemzése... ⏳")

    try:
        result = await _get_result(competition=command)
        report = format_league_report(result, command)
        await _send_long_message(update, report)
    except Exception as e:
        logger.error("/%s hiba: %s", command.lower(), e, exc_info=True)
        await update.message.reply_text(f"Hiba: {e}")
