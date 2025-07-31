# -*- coding: utf-8 -*-
import os
import json
import asyncio
import threading
from flask import Flask
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    ContextTypes,
    CommandHandler,
    MessageHandler,
    filters,
)

DATA_FILE = "data.json"
TIMEOUT_SECONDS = 2.5 * 60 * 60  # 2.5 часа

# Define globals BEFORE functions
machines = {"Белая": [], "Чёрная": [], "Роба": []}
timeouts = {}
user_ids = {}

main_menu = [["Белая", "Чёрная", "Роба"],
             ["📋 Очередь", "🔄 Статус"],
             ["🚪 Покинуть очередь", "🧼 Завершил стирку"]]
back_button = [["⬅️ Назад"]]
main_reply = ReplyKeyboardMarkup(main_menu, resize_keyboard=True)
back_reply = ReplyKeyboardMarkup(back_button, resize_keyboard=True)

def load_data():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"Белая": [], "Чёрная": [], "Роба": []}

def save_data():
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(machines, f, ensure_ascii=False, indent=2)

def start_timeout(machine, user, app):
    if machine in timeouts:
        timeouts[machine].cancel()

    async def task():
        await asyncio.sleep(TIMEOUT_SECONDS)
        if machines[machine] and machines[machine][0] == user:
            machines[machine].pop(0)
            save_data()
            if user in user_ids:
                await app.bot.send_message(chat_id=user_ids[user],
                                           text=f"⏰ Время вышло. Ты удалён из очереди на {machine}.")
            await notify_next(machine, app)

    timeouts[machine] = asyncio.create_task(task())

async def notify_next(machine, app):
    if machines[machine]:
        next_user = machines[machine][0]
        if next_user in user_ids:
            await app.bot.send_message(chat_id=user_ids[next_user],
                                       text=f"🧺 Теперь ты первый в очереди на {machine}!")
            start_timeout(machine, next_user, app)

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    username = update.effective_user.username or update.effective_user.first_name
    user_ids[username] = update.effective_user.id
    await update.message.reply_text("Привет! Выбери машинку:", reply_markup=main_reply)

async def cmd_reset(update: Update, context: ContextTypes.DEFAULT_TYPE):
    for m in machines:
        machines[m] = []
    save_data()
    await update.message.reply_text("Очереди сброшены.", reply_markup=main_reply)

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    username = user.username or user.first_name
    user_ids[username] = user.id
    text = update.message.text

    if text == "⬅️ Назад":
        await update.message.reply_text("Главное меню:", reply_markup=main_reply)
        return

    if text == "🔄 Статус":
        status = [f"{m}: {machines[m][0] if machines[m] else 'Свободна'}" for m in machines]
        await update.message.reply_text(
            "Статус машин:\n" + "\n".join(status),
            reply_markup=back_reply
        )
        return

    if text == "📋 Очередь":
        info = [f"{m}:\n" + ("\n".join(machines[m]) if machines[m] else "— пусто") for m in machines]
        await update.message.reply_text(
            "Очереди:\n\n" + "\n\n".join(info),
            reply_markup=back_reply
        )
        return

    if text == "🚪 Покинуть очередь":
        removed = []
        for m in machines:
            if username in machines[m]:
                was_first = machines[m][0] == username
                machines[m].remove(username)
                if was_first:
                    await notify_next(m, context.application)
                removed.append(m)
        save_data()
        msg = f"🚪 Покинул: {', '.join(removed)}" if removed else "Ты не в очереди."
        await update.message.reply_text(msg, reply_markup=back_reply)
        return

    if text == "🧼 Завершил стирку":
        done = []
        for m in machines:
            if machines[m] and machines[m][0] == username:
                machines[m].pop(0)
                if m in timeouts:
                    timeouts[m].cancel()
                await notify_next(m, context.application)
                done.append(m)
        save_data()
        msg = f"✅ Завершено: {', '.join(done)}" if done else "Ты не первый ни на одной машине."
        await update.message.reply_text(msg, reply_markup=back_reply)
        return

    if text in machines:
        if username in machines[text]:
            pos = machines[text].index(username) + 1
            await update.message.reply_text(f"Ты уже в очереди на {text}, позиция: {pos}", reply_markup=back_reply)
        else:
            machines[text].append(username)
            save_data()
            pos = len(machines[text])
            if pos == 1:
                await update.message.reply_text(
                    f"✅ Ты записан на {text}.\nТы первый!\n⏰ У тебя есть 2.5 часа.",
                    reply_markup=back_reply)
                start_timeout(text, username, context.application)
            else:
                await update.message.reply_text(
                    f"🔔 Ты в очереди на {text}, твоя позиция: {pos}", reply_markup=back_reply)
        return

    await update.message.reply_text("Выбери действие из меню:", reply_markup=main_reply)

# Flask health check for Render keep-alive
app_flask = Flask(__name__)

@app_flask.route("/")
@app_flask.route("/health")
def health():
    return "ok", 200

def run_flask():
    port = int(os.environ.get("PORT", 10000))
    app_flask.run(host="0.0.0.0", port=port)

def main():
    # Use the global machines
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