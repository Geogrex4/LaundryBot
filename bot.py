import asyncio
import json
import os
from aiogram import Bot, Dispatcher, types
from aiogram.filters import CommandStart, Command
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
from aiogram.enums import ParseMode

TOKEN = os.getenv("BOT_TOKEN")
DATA_FILE = "data.json"
TIMEOUT = 2.5 * 60 * 60

machines = {"Белая": [], "Чёрная": [], "Роба": []}
timeouts = {}
user_ids = {}

main_menu = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="Белая"), KeyboardButton(text="Чёрная"), KeyboardButton(text="Роба")],
        [KeyboardButton(text="📋 Очередь"), KeyboardButton(text="🔄 Статус")],
        [KeyboardButton(text="🚪 Покинуть очередь"), KeyboardButton(text="🧼 Завершил стирку")]
    ],
    resize_keyboard=True
)

back_menu = ReplyKeyboardMarkup(
    keyboard=[[KeyboardButton(text="⬅️ Назад")]],
    resize_keyboard=True
)


def load_data():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"Белая": [], "Чёрная": [], "Роба": []}


def save_data():
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(machines, f, ensure_ascii=False, indent=2)


async def notify_next(bot: Bot, machine: str):
    if machines[machine]:
        next_user = machines[machine][0]
        if next_user in user_ids:
            await bot.send_message(user_ids[next_user], f"🧺 Теперь ты первый в очереди на {machine}!")
            await start_timeout(bot, machine, next_user)


async def start_timeout(bot: Bot, machine: str, username: str):
    if machine in timeouts:
        timeouts[machine].cancel()

    async def task():
        await asyncio.sleep(TIMEOUT)
        if machines[machine] and machines[machine][0] == username:
            machines[machine].pop(0)
            save_data()
            if username in user_ids:
                await bot.send_message(user_ids[username], f"⏰ Время вышло. Ты удалён из очереди на {machine}.")
            await notify_next(bot, machine)

    timeouts[machine] = asyncio.create_task(task())


dp = Dispatcher()


@dp.message(CommandStart())
async def handle_start(message: types.Message):
    username = message.from_user.username or message.from_user.first_name
    user_ids[username] = message.from_user.id
    await message.answer("Привет! Выбери машинку:", reply_markup=main_menu)


@dp.message(Command("reset"))
async def handle_reset(message: types.Message):
    for m in machines:
        machines[m] = []
    save_data()
    await message.answer("Очереди сброшены.", reply_markup=main_menu)


@dp.message()
async def handle_message(message: types.Message):
    username = message.from_user.username or message.from_user.first_name
    user_ids[username] = message.from_user.id
    text = message.text

    if text == "⬅️ Назад":
        await message.answer("Главное меню:", reply_markup=main_menu)

    elif text == "📋 Очередь":
        lines = []
        for m in machines:
            queue = "\n".join(machines[m]) if machines[m] else "— пусто"
            lines.append(f"{m}:\n{queue}")
        await message.answer("\n\n".join(lines), reply_markup=back_menu)

    elif text == "🔄 Статус":
        lines = [f"{m}: {machines[m][0] if machines[m] else 'Свободна'}" for m in machines]
        await message.answer("\n".join(lines), reply_markup=back_menu)

    elif text == "🚪 Покинуть очередь":
        removed = []
        for m in machines:
            if username in machines[m]:
                was_first = machines[m][0] == username
                machines[m].remove(username)
                if was_first:
                    await notify_next(message.bot, m)
                removed.append(m)
        save_data()
        if removed:
            await message.answer(f"🚪 Покинул: {', '.join(removed)}", reply_markup=back_menu)
        else:
            await message.answer("Ты не в очереди.", reply_markup=back_menu)

    elif text == "🧼 Завершил стирку":
        done = []
        for m in machines:
            if machines[m] and machines[m][0] == username:
                machines[m].pop(0)
                if m in timeouts:
                    timeouts[m].cancel()
                await notify_next(message.bot, m)
                done.append(m)
        save_data()
        if done:
            await message.answer(f"✅ Завершено: {', '.join(done)}", reply_markup=back_menu)
        else:
            await message.answer("Ты не первый ни на одной машине.", reply_markup=back_menu)

    elif text in machines:
        if username in machines[text]:
            pos = machines[text].index(username) + 1
            await message.answer(f"Ты уже в очереди на {text}, позиция: {pos}", reply_markup=back_menu)
        else:
            machines[text].append(username)
            save_data()
            pos = len(machines[text])
            if pos == 1:
                await message.answer(
                    f"✅ Ты записан на {text}. Ты первый!\n⏰ У тебя есть 2.5 часа.",
                    reply_markup=back_menu
                )
                await start_timeout(message.bot, text, username)
            else:
                await message.answer(
                    f"🔔 Ты в очереди на {text}, твоя позиция: {pos}",
                    reply_markup=back_menu
                )
    else:
        await message.answer("Выбери действие из меню:", reply_markup=main_menu)


async def main():
    global machines
    machines.update(load_data())
    bot = Bot(token=TOKEN, parse_mode=ParseMode.HTML)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
