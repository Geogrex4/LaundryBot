import os
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters
)
import sqlite3
from datetime import datetime, timedelta
import pytz

# Токен вашего бота
TOKEN = "8284770588:AAFzVy5K31zCul4vnXqFKW7moTVLN-Y1pTs"

# Настройка базы данных
DB_NAME = "laundry_bot.db"

# Состояния разговора
CHOOSING_MACHINE, CHOOSING_ACTION, CHOOSING_TIME, CHOOSING_DATE, VIEW_SCHEDULE, MANAGING_WASH = range(6)

# Тюменское время (Asia/Yekaterinburg)
TZ = pytz.timezone('Asia/Yekaterinburg')

# Инициализация базы данных
def init_db():
    # ... (осталось без изменений)

# Сохраняем пользователя
def save_user(user_id, username, full_name):
    # ... (осталось без изменений)

# Функции для работы с очередью
# ... (все функции остались без изменений)

# Telegram обработчики
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user = update.effective_user
    save_user(user.id, user.username, user.full_name)
    
    keyboard = [
        [InlineKeyboardButton("Встать в очередь", callback_data='join_queue')],
        [InlineKeyboardButton("Покинуть очередь", callback_data='leave_queue')],
        [InlineKeyboardButton("Посмотреть расписание", callback_data='view_schedule')],
        [InlineKeyboardButton("Управление стиркой", callback_data='manage_wash')]
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    if update.message:
        await update.message.reply_text(
            f"Привет, {user.full_name}! Я бот для управления очередью к стиральным машинам.",
            reply_markup=reply_markup
        )
    else:
        await update.callback_query.edit_message_text(
            f"Привет, {user.full_name}! Я бот для управления очередью к стиральным машинам.",
            reply_markup=reply_markup
        )
    return CHOOSING_ACTION

async def join_queue(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    
    keyboard = [
        [InlineKeyboardButton("Машинка 1", callback_data='machine_1')],
        [InlineKeyboardButton("Машинка 2", callback_data='machine_2')],
        [InlineKeyboardButton("Роба", callback_data='machine_3')],
        [InlineKeyboardButton("Назад", callback_data='back')]
    ]
    
    await query.edit_message_text(
        text="Выберите стиральную машину:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return CHOOSING_MACHINE

async def choose_time(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    machine_id = int(query.data.split('_')[1])
    context.user_data['machine_id'] = machine_id
    
    # Текущее время в Тюмени
    now = datetime.now(TZ)
    
    # Генерируем кнопки с временными слотами
    keyboard = []
    for i in range(8):  # На 16 часов вперед
        time_slot = now + timedelta(hours=i)
        # Пропускаем ночное время (с 23:00 до 8:00)
        if time_slot.hour >= 23 or time_slot.hour < 8:
            continue
        keyboard.append([
            InlineKeyboardButton(
                time_slot.strftime("%H:%M"),
                callback_data=f"time_{time_slot.timestamp()}"
            )
        ])
    
    keyboard.append([InlineKeyboardButton("Назад", callback_data='back_choose_machine')])
    
    await query.edit_message_text(
        text="Выберите время начала стирки:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return CHOOSING_TIME

async def confirm_booking(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    timestamp = float(query.data.split('_')[1])
    start_time = datetime.fromtimestamp(timestamp, tz=TZ)
    
    user_id = update.effective_user.id
    machine_id = context.user_data['machine_id']
    
    add_to_queue(user_id, machine_id, start_time)
    
    await query.edit_message_text(
        text=f"✅ Вы записаны на {start_time.strftime('%d.%m.%Y %H:%M')}!\n"
             "Вы получите уведомление за 10 минут до начала."
    )
    return await start(update, context)

async def leave_queue(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    remove_from_queue(user_id)
    
    if update.callback_query:
        query = update.callback_query
        await query.answer()
        await query.edit_message_text("❌ Вы вышли из очереди!")
    else:
        await update.message.reply_text("❌ Вы вышли из очереди!")
    await start(update, context)

def notify_next_user(context, machine_id: int):
    next_user = get_next_user(machine_id)
    if next_user:
        context.bot.send_message(
            chat_id=next_user[1],
            text=f"⏰ Ваша очередь подходит! Машинка освободилась."
        )

async def manage_wash(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    
    keyboard = [
        [InlineKeyboardButton("Закончил стирку", callback_data='finish_wash')],
        [InlineKeyboardButton("Срочное сообщение", callback_data='urgent_message')],
        [InlineKeyboardButton("Назад", callback_data='back')]
    ]
    
    await query.edit_message_text(
        text="Управление стиркой:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    return MANAGING_WASH

async def finish_wash(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    
    keyboard = [
        [InlineKeyboardButton("Машинка 1", callback_data='finish_1')],
        [InlineKeyboardButton("Машинка 2", callback_data='finish_2')],
        [InlineKeyboardButton("Роба", callback_data='finish_3')],
        [InlineKeyboardButton("Назад", callback_data='back_manage_wash')]
    ]
    
    await query.edit_message_text(
        text="Какую машинку вы освободили?",
        reply_markup=InlineKeyboardMarkup(keyboard)
    return MANAGING_WASH

async def process_finish(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    machine_id = int(query.data.split('_')[1])
    
    finish_washing(machine_id)
    notify_next_user(context, machine_id)
    
    await query.edit_message_text("✅ Статус обновлен! Следующий пользователь уведомлен.")
    await start(update, context)

async def urgent_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    
    keyboard = [
        [InlineKeyboardButton("Машинка 1", callback_data='urgent_1')],
        [InlineKeyboardButton("Машинка 2", callback_data='urgent_2')],
        [InlineKeyboardButton("Роба", callback_data='urgent_3')],
        [InlineKeyboardButton("Назад", callback_data='back_manage_wash')]
    ]
    
    await query.edit_message_text(
        text="К какой машинке срочное сообщение?",
        reply_markup=InlineKeyboardMarkup(keyboard))
    return MANAGING_WASH

async def send_urgent_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    machine_id = int(query.data.split('_')[1])
    
    current_user = get_current_user(machine_id)
    if current_user:
        await context.bot.send_message(
            chat_id=current_user[1],
            text="🚨 СРОЧНО! Пожалуйста, подойдите к стиральной машине!"
        )
        await query.edit_message_text("✅ Сообщение отправлено!")
    else:
        await query.edit_message_text("❌ Никто не использует эту машинку сейчас.")
    await start(update, context)

async def view_schedule(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    
    keyboard = [
        [InlineKeyboardButton("Сегодня", callback_data='schedule_today')],
        [InlineKeyboardButton("Завтра", callback_data='schedule_tomorrow')],
        [InlineKeyboardButton("Назад", callback_data='back')]
    ]
    
    await query.edit_message_text(
        text="Просмотр расписания:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    return VIEW_SCHEDULE

async def show_schedule(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    
    # Определяем дату для показа
    if 'today' in query.data:
        date = datetime.now(TZ)
    elif 'tomorrow' in query.data:
        date = datetime.now(TZ) + timedelta(days=1)
    else:
        date = datetime.now(TZ)
    
    schedule = get_schedule(date)
    
    if not schedule:
        text = f"📅 На {date.strftime('%d.%m.%Y')} записей нет"
    else:
        text = f"📅 Расписание на {date.strftime('%d.%m.%Y')}:\n\n"
        current_machine = None
        
        for entry in schedule:
            machine_name, start_time, end_time, user_name = entry
            if isinstance(start_time, str):
                start_time = datetime.fromisoformat(start_time).astimezone(TZ)
            if isinstance(end_time, str):
                end_time = datetime.fromisoformat(end_time).astimezone(TZ)
            
            if machine_name != current_machine:
                text += f"\n🧺 <b>{machine_name}:</b>\n"
                current_machine = machine_name
            
            text += f"⏰ {start_time.strftime('%H:%M')}-{end_time.strftime('%H:%M')} - {user_name}\n"
    
    keyboard = [[InlineKeyboardButton("Назад", callback_data='back_view_schedule')]]
    await query.edit_message_text(text=text, 
                                 reply_markup=InlineKeyboardMarkup(keyboard),
                                 parse_mode='HTML')
    return VIEW_SCHEDULE

async def back_to_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    return await start(update, context)

async def back_choose_machine(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    return await join_queue(update, context)

async def back_manage_wash(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    return await manage_wash(update, context)

async def back_view_schedule(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    return await view_schedule(update, context)

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text('Действие отменено')
    return ConversationHandler.END

def main() -> None:
    logging.basicConfig(
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        level=logging.INFO
    )
    
    init_db()
    
    # Создаем Application
    application = Application.builder().token(TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('start', start)],
        states={
            CHOOSING_ACTION: [
                CallbackQueryHandler(join_queue, pattern='^join_queue$'),
                CallbackQueryHandler(leave_queue, pattern='^leave_queue$'),
                CallbackQueryHandler(view_schedule, pattern='^view_schedule$'),
                CallbackQueryHandler(manage_wash, pattern='^manage_wash$'),
                CallbackQueryHandler(back_to_menu, pattern='^back$')
            ],
            CHOOSING_MACHINE: [
                CallbackQueryHandler(choose_time, pattern='^machine_'),
                CallbackQueryHandler(back_to_menu, pattern='^back$')
            ],
            CHOOSING_TIME: [
                CallbackQueryHandler(confirm_booking, pattern='^time_'),
                CallbackQueryHandler(back_choose_machine, pattern='^back_choose_machine$')
            ],
            VIEW_SCHEDULE: [
                CallbackQueryHandler(show_schedule, pattern='^schedule_'),
                CallbackQueryHandler(back_to_menu, pattern='^back_view_schedule$'),
                CallbackQueryHandler(back_to_menu, pattern='^back$')
            ],
            MANAGING_WASH: [
                CallbackQueryHandler(finish_wash, pattern='^finish_wash$'),
                CallbackQueryHandler(urgent_message, pattern='^urgent_message$'),
                CallbackQueryHandler(process_finish, pattern='^finish_'),
                CallbackQueryHandler(send_urgent_message, pattern='^urgent_'),
                CallbackQueryHandler(back_to_menu, pattern='^back_manage_wash$'),
                CallbackQueryHandler(back_to_menu, pattern='^back$')
            ]
        },
        fallbacks=[CommandHandler('cancel', cancel)]
    )

    application.add_handler(conv_handler)
    application.run_polling()

if __name__ == '__main__':
    main()
