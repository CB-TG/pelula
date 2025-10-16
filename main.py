from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
import asyncio
import re
from database import init_db, set_reminder_time, get_reminder_time, log_action, get_logs_for_month
from scheduler import ReminderScheduler
from utils import format_date, format_time

# Конфигурация
BOT_TOKEN = "8348451136:AAFZ9C49lELJ97U-3IvMMPsT_-CsFPwbkjs"  # Заменить на токен
bot = Bot(token=BOT_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)
scheduler = ReminderScheduler(bot)

# Глобальное хранилище данных пользователя (в реальных проектах используй БД)
user_data = {}

def get_or_create_user_data(user_id):
    if user_id not in user_data:
        user_data[user_id] = {}
    return user_data[user_id]

def save_user_data(user_id, data):
    user_data[user_id] = data

class WaitingForTime(StatesGroup):
    waiting_for_time = State()

@dp.message(Command("start"))
async def cmd_start(message: types.Message, state: FSMContext):
    await message.answer("Привет! В какое время тебе нужно напоминать о таблетке? Введи в формате ЧЧ:ММ (например, 14:30).")
    await state.set_state(WaitingForTime.waiting_for_time)

@dp.message(WaitingForTime.waiting_for_time)
async def process_time(message: types.Message, state: FSMContext):
    time_str = message.text
    if not re.match(r"^\d{2}:\d{2}$", time_str):
        await message.answer("Неправильный формат. Введи время в формате ЧЧ:ММ (например, 14:30).")
        return
    hour, minute = map(int, time_str.split(":"))
    if hour > 23 or minute > 59:
        await message.answer("Неправильное время. Введи корректное время.")
        return
    user_id = message.from_user.id
    await set_reminder_time(user_id, time_str)
    await scheduler.schedule_reminder(user_id)
    await message.answer(f"Время напоминания установлено на {time_str}.")
    await state.clear()

@dp.message(lambda msg: msg.text == "Изменить")
async def cmd_change_time(message: types.Message, state: FSMContext):
    await cmd_start(message, state)

@dp.message(lambda msg: msg.text.startswith("Расписание "))
async def cmd_schedule(message: types.Message):
    user_id = message.from_user.id
    parts = message.text.split(" ", 1)
    if len(parts) != 2:
        await message.answer("Формат: Расписание мм.гг (например, Расписание 10.25)")
        return
    mm_yy = parts[1]
    try:
        mm, yy = mm_yy.split(".")
        logs = await get_logs_for_month(user_id, mm, yy)
        if not logs:
            await message.answer("Нет данных за этот месяц.")
            return
        response = f"Расписание за {mm}.{yy}:\n"
        for date, status, time_taken in logs:
            time_str = f" в {time_taken}" if time_taken else ""
            response += f"- {date}: {status}{time_str}\n"
        await message.answer(response)
    except Exception:
        await message.answer("Формат: Расписание мм.гг (например, Расписание 10.25)")

@dp.callback_query(lambda c: c.data in ["taken", "not_taken", "skip_today"])
async def handle_callback(callback_query: types.CallbackQuery):
    user_id = callback_query.from_user.id
    data = get_or_create_user_data(user_id)
    date = format_date()
    time = format_time()

    if callback_query.data == "taken":
        await log_action(user_id, date, "taken", time)
        await callback_query.answer("Спасибо!")
        # Отменить повторы
        task = data.get("repeat_task")
        if task:
            task.cancel()
            data.pop("repeat_task", None)
            save_user_data(user_id, data)

    elif callback_query.data == "not_taken":
        await callback_query.answer("Напомню снова через полчаса.")
        # Через 30 мин снова задать вопрос
        scheduler.scheduler.add_job(
            scheduler.ask_if_taken,
            'date',
            run_date=asyncio.get_event_loop().time() + 1800,
            args=[user_id],
            id=f"ask_{user_id}_retry"
        )

    elif callback_query.data == "skip_today":
        await log_action(user_id, date, "not_needed", time)
        await callback_query.answer("Напоминания отключены до следующего дня.")
        data["skip_today"] = True
        save_user_data(user_id, data)

    # Удалить сообщение
    try:
        await bot.delete_message(user_id, callback_query.message.message_id)
    except Exception:
        pass

async def main():
    await init_db()
    await scheduler.start_scheduler()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())