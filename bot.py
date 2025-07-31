import os
import json
import asyncio
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

DATA_FILE = "data.json"
TIMEOUT_SECONDS = 2.5 * 60 * 60  # 2.5 часа

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


def start_timeout(machine_name, username, context: ContextTypes.DEFAULT_TYPE):
    if machine_name in timeouts:
        timeouts[machine_name].cancel()

    async def timeout_task():
        await asyncio.sleep(TIMEOUT_SECONDS)
        if machines[machine_name] and machines[machine_name][0] == username:
            machines[machine_name].pop(0)
            save_data()
            chat_id = user_ids.get(username)
            if chat_id:
                await context.bot.send_message(
                    chat_id=chat_id,
                    text=f"⏰ Время вышло. Ты удалён из очереди на {machine_name}."
                )
            await notify_next(machine_name, context)

    timeouts[machine_name] = asyncio.create_task(timeout_task())


async def notify_next(machine_name, context: ContextTypes.DEFAULT_TYPE):
    queue = machines[machine_name]
    if queue:
        next_user = queue[0]
        chat_id = user_ids.get(next_user)
        if chat_id:
            await context.bot.send_message(
                chat_id=chat_id,
                text=f"🧺 Теперь ты первый в очереди на {machine_name}!"
            )
            start_timeout(machine_name, next_user, context)


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    username = user.username or user.first_name
    user_ids[username] = user.id
    await update.message.reply_text("Привет! Выбери машинку:", reply_markup=main_reply)


async def cmd_reload(update: Update, context: ContextTypes.DEFAULT_TYPE):
    username = update.effective_user.username or update.effective_user.first_name
    user_ids[username] = update.effective_user.id
    await update.message.reply_text("🔁 Бот перезагружен!", reply_markup=main_reply)


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
        status_lines = [f"{m}: {machines[m][0] if machines[m] else 'Свободна'}" for m in machines]
        await update.message.reply_text("Статус машин:\n" + "\n".join(status_lines), reply_markup=back_reply)
        return

    if text == "📋 Очередь":
        queue_text = "\n\n".join([f"{m}:\n" + ("\n".join(machines[m]) if machines[m] else "— пусто") for m in machines])
        await update.message.reply_text("Очереди:\n" + queue_text, reply_markup=back_reply)
        return

    if text == "🚪 Покинуть очередь":
        left_machines = []
        for m in machines:
            if username in machines[m]:
                was_first = machines[m][0] == username
                machines[m].remove(username)
                if was_first:
                    await notify_next(m, context)
                left_machines.append(m)
        save_data()
        msg = f"🚪 Покинул: {', '.join(left_machines)}" if left_machines else "Ты не в очереди."
        await update.message.reply_text(msg, reply_markup=back_reply)
        return

    if text == "🧼 Завершил стирку":
        done = []
        for m in machines:
            if machines[m] and machines[m][0] == username:
                machines[m].pop(0)
                if m in timeouts:
                    timeouts[m].cancel()
                await notify_next(m, context)
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
                    f"✅ Ты записан на {text}.\nТы первый!\n⏰ У тебя есть 2.5 часа до автоматического удаления.",
                    reply_markup=back_reply)
                start_timeout(text, username, context)
            else:
                await update.message.reply_text(
                    f"🔔 Ты в очереди на {text}, твоя позиция: {pos}",
                    reply_markup=back_reply)
        return

    await update.message.reply_text("Выбери действие из меню:", reply_markup=main_reply)


async def main():
    global machines
    machines.update(load_data())

    app = Application.builder().token(os.environ["BOT_TOKEN"]).build()

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("reload", cmd_reload))
    app.add_handler(CommandHandler("reset", cmd_reset))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    await app.run_polling()


if __name__ == "__main__":
    asyncio.run(main())
