"""Telegram bot interface for Hecko.

Runs alongside the voice assistant in a background thread, sharing the same
command router and state (timers, reminders, sleep mode, etc.).

Requires telegram_credentials.py with TELEGRAM_TOKEN from @BotFather.
If not configured, start_telegram() logs a message and returns without error.
"""

import re
import threading
import asyncio
from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, filters, ContextTypes

from hecko.commands import router

_SOUND_MARKER = re.compile(r"\[\[.*?\]\]")


def _clean_response(text):
    """Strip [[sound.mp3]] markers from response text."""
    return _SOUND_MARKER.sub("", text).strip()


def _log(msg):
    print(msg, flush=True)


async def _handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle an incoming Telegram message."""
    text = update.message.text
    if not text:
        return

    user = update.message.from_user
    username = user.first_name or user.username or "unknown"
    source = f"[Telegram:{username}]"

    _log(f"  {source} \"{text}\"")

    response, scores = router.dispatch(text, source=source)

    if response is None:
        _log("  (sleeping — ignored)")
        return

    if scores:
        score_str = ", ".join(f"{name}={s:.2f}" for name, s in scores)
        _log(f"  Scores: {score_str}")

    cleaned = _clean_response(response)
    _log(f"  Response: \"{cleaned}\"")

    if cleaned:
        await update.message.reply_text(cleaned)


async def _run_bot_async(token):
    """Run the Telegram bot polling loop (async)."""
    app = ApplicationBuilder().token(token).build()
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, _handle_message))

    await app.initialize()
    await app.updater.start_polling(drop_pending_updates=True)
    await app.start()
    print("Telegram bot started.", flush=True)

    # Block forever (until thread is killed as daemon)
    stop_event = asyncio.Event()
    await stop_event.wait()


def _run_bot(token):
    """Run the Telegram bot (blocking). Meant to be called in a thread."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(_run_bot_async(token))


def start_telegram():
    """Start the Telegram bot in a background daemon thread.

    Returns True if started, False if skipped (no token).
    """
    try:
        from hecko.telegram_credentials import TELEGRAM_TOKEN as token
    except ImportError:
        print("No telegram_credentials.py — Telegram disabled.", flush=True)
        return False

    t = threading.Thread(target=_run_bot, args=(token,), daemon=True)
    t.start()
    return True
