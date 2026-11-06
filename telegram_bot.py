"""
telegram_bot.py — thin Telegram client for the Mika backend.

Every Telegram user gets their own memory thread, keyed by their Telegram
user ID, by calling the SAME /chat/{user_id} endpoint the avatar app uses.
So if you message Mika on Telegram and then open the avatar app signed in
as "the same user" (same user_id), she remembers both conversations.

Setup:
  1. Message @BotFather on Telegram, send /newbot, follow the prompts,
     copy the bot token it gives you.
  2. pip install -r requirements.txt   (python-telegram-bot added below)
  3. export TELEGRAM_BOT_TOKEN=xxxx
     export BACKEND_URL=https://your-service-name.onrender.com
  4. python telegram_bot.py

Deploy this as its OWN Render web service (or background worker) pointing
at the same backend's BACKEND_URL — it's a separate small process.
"""

import os
import logging
import requests
from telegram import Update
from telegram.ext import ApplicationBuilder, ContextTypes, MessageHandler, CommandHandler, filters

logging.basicConfig(level=logging.INFO)

BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
BACKEND_URL = os.environ.get("BACKEND_URL", "http://localhost:8000").rstrip("/")


def ask_mika(user_id: str, message: str) -> str:
    """Calls the shared backend's HTTP chat endpoint."""
    resp = requests.post(
        f"{BACKEND_URL}/chat/{user_id}",
        json={"message": message},
        timeout=60,  # free-tier cold starts can be slow on the first call
    )
    resp.raise_for_status()
    data = resp.json()
    reply = data.get("reply", "...")
    action = data.get("action")
    if action:
        reply += f"\n\n_({action})_"
    return reply


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Hi, I'm Mika! Just message me normally and I'll remember our "
        "conversation across chats."
    )


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)  # unique per Telegram user
    user_text = update.message.text

    await update.message.chat.send_action("typing")
    try:
        reply = ask_mika(user_id, user_text)
    except requests.exceptions.RequestException as e:
        reply = f"(Couldn't reach my backend right now: {e})"

    await update.message.reply_text(reply, parse_mode="Markdown")


def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    print("Mika Telegram bot running...")
    app.run_polling()


if __name__ == "__main__":
    main()
