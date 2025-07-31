import os
import json
import asyncio
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    ContextTypes,
    CommandHandler,
    MessageHandler,
    filters,
)
from flask import Flask
import threading

# ... (rest of your existing bot code, unchanged) ...

app_flask = Flask(__name__)

@app_flask.route("/")
@app_flask.route("/health")
def health():
    return "ok", 200

def run_flask():
    port = int(os.environ.get("PORT", 10000))
    app_flask.run(host="0.0.0.0", port=port)

def main():
    global machines
    machines.update(load_data())

    token = os.environ.get("BOT_TOKEN")
    if not token:
        raise RuntimeError("BOT_TOKEN not set in environment variables")

    application = ApplicationBuilder().token(token).build()

    application.add_handler(CommandHandler("start", cmd_start))
    application.add_handler(CommandHandler("reset", cmd_reset))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    # Start Flask server in a background thread
    threading.Thread(target=run_flask, daemon=True).start()

    application.run_polling()

if __name__ == "__main__":
    main()