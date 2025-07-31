
import json
import os
import asyncio
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters

DATA_FILE = "data.json"
TIMEOUT_SECONDS = 2.5 * 60 * 60  # 2.5 часа

machines = {
    "Белая": [],
    "Чёрная": [],
    "Роба": []
}
timeouts = {}  # machine_name -> asyncio.Task
user_ids = {}  # username -> telegram_id

# Загрузка и сохранение
def load_data():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"Белая": [], "Чёрная": [], "Роба": []}

def save_data():
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(machines, f, ensure_ascii=False, indent=2)

# Интерфейс
main_menu = [["Белая", "Чёрная", "Роба"],
             ["📋 Очередь", "🔄 Статус"],
             ["🚪 Покинуть очередь", "🧼 Завершил стирку"]]
back_button = [["⬅️ Назад"]]

main_reply = ReplyKeyboardMarkup(main_menu, resize_keyboard=True)
back_reply = ReplyKeyboardMarkup(back_button, resize_keyboard=True)

# Отправка уведомления следующему
async def notify_next(machine_name, context):
    queue = machines[machine_name]
    if queue:
        next_user = queue[0]
        if next_user in user_ids:
            await context.bot.send_message(
                chat_id=user_ids[next_user],
                text=f"🧺 Ты теперь первый в очереди на {machine_name}!"
            )
        # Запускаем таймер
        start_timeout(machine_name, next_user, context)

# Таймер удаления после 2.5 часов
def start_timeout(machine_name, username, context):
    if machine_name in timeouts:
        timeouts[machine_name].cancel()

    async def timeout_task():
        try:
            await asyncio.sleep(TIMEOUT_SECONDS)
            if machines[machine_name] and machines[machine_name][0] == username:
                machines[machine_name].pop(0)
                save_data()
                await context.bot.send_message(
                    chat_id=user_ids.get(username),
                    text=f"⏰ Время стирки на {machine_name} истекло. Ты был автоматически удалён из очереди."
                )
                await notify_next(machine_name, context)
        except asyncio.CancelledError:
            pass

    task = asyncio.create_task(timeout_task())
    timeouts[machine_name] = task

# Команды
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.message.from_user
    username = user.username or user.first_name
    user_ids[username] = user.id
    await update.message.reply_text("Привет! Выбери машинку или действие:", reply_markup=main_reply)

async def cmd_reload(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.message.from_user
    username = user.username or user.first_name
    user_ids[username] = user.id
    await update.message.reply_text("🔁 Перезагрузка завершена. Главное меню:", reply_markup=main_reply)

async def cmd_reset(update: Update, context: ContextTypes.DEFAULT_TYPE):
    for name in machines:
        machines[name] = []
    save_data()
    await update.message.reply_text("Очереди сброшены.", reply_markup=main_reply)

# Сообщения
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.message.from_user
    username = user.username or user.first_name
    user_ids[username] = user.id
    text = update.message.text

    if text == "⬅️ Назад":
        await update.message.reply_text("Главное меню:", reply_markup=main_reply)
        return

    if text == "🔄 Статус":
        status = "\n".join([f"{m}: {machines[m][0] if machines[m] else 'Свободна'}" for m in machines])
        await update.message.reply_text("Статус машинок:\n" + status, reply_markup=back_reply)
        return

    if text == "📋 Очередь":
        q = ""
        for m, queue in machines.items():
            q += f"{m}:\n" + ("\n".join([f" - {u}" for u in queue]) if queue else " - пусто") + "\n\n"
        await update.message.reply_text(q.strip(), reply_markup=back_reply)
        return

    if text == "🚪 Покинуть очередь":
        left = []
        for name in machines:
            if username in machines[name]:
                was_first = machines[name][0] == username
                machines[name].remove(username)
                left.append(name)
                if was_first:
                    await notify_next(name, context)
        save_data()
        msg = f"🚪 Ты покинул очереди: {', '.join(left)}." if left else "Ты не стоишь ни в одной очереди."
        await update.message.reply_text(msg, reply_markup=back_reply)
        return

    if text == "🧼 Завершил стирку":
        done = []
        for name in machines:
            if machines[name] and machines[name][0] == username:
                machines[name].pop(0)
                done.append(name)
                await notify_next(name, context)
                if name in timeouts:
                    timeouts[name].cancel()
        save_data()
        msg = f"✅ Завершено: {', '.join(done)}." if done else "Ты не был первым ни на одной машинке."
        await update.message.reply_text(msg, reply_markup=back_reply)
        return

    if text in machines:
        queue = machines[text]
        if username in queue:
            pos = queue.index(username) + 1
            await update.message.reply_text(
                f"Ты уже в очереди к {text}. Позиция: {pos}", reply_markup=back_reply)
        else:
            queue.append(username)
            save_data()
            pos = len(queue)
            if pos == 1:
                await update.message.reply_text(
                    f"✅ Ты записан на {text}. Ты первый!\n\n⏰ У тебя есть 2.5 часа. "
                    f"Если не нажмёшь «🧼 Завершил стирку», тебя удалит автоматически.",
                    reply_markup=back_reply)
                start_timeout(text, username, context)
            else:
                await update.message.reply_text(
                    f"🔔 Ты записан в очередь к {text}. Твоя позиция: {pos}.", reply_markup=back_reply)
        return

    await update.message.reply_text("Выбери действие из меню.", reply_markup=main_reply)

# Запуск
def main():
    global machines
    machines.update(load_data())

    import os
    app = Application.builder().token(os.environ["BOT_TOKEN"]).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("reload", cmd_reload))
    app.add_handler(CommandHandler("reset", cmd_reset))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    print("Бот запущен.")
    app.run_polling()

if __name__ == "__main__":
    main()
