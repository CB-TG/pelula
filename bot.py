# bot.py
import asyncio
import logging
import re
from datetime import datetime, timedelta
from typing import Optional
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from tzlocal import get_localzone
from zoneinfo import ZoneInfo

from database import (
    init_db,
    set_reminder_time,
    get_reminder_time,
    log_pill,
    get_logs_for_month,
    get_user_timings,
    update_timing
)
from scheduler import send_pill_reminder, send_check_message, cancel_all_jobs

# Глобальное хранилище для данных проверки (альтернатива dp.storage)
user_check_data = {}

# === НАСТРОЙКИ ===
BOT_TOKEN = "8348451136:AAFZ9C49lELJ97U-3IvMMPsT_-CsFPwbkjs"  # ← ОБЯЗАТЕЛЬНО ЗАМЕНИ НА СВОЙ!
TIMEZONE = ZoneInfo("Europe/Moscow")

logging.basicConfig(level=logging.INFO)
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
scheduler_global = AsyncIOScheduler(timezone=TIMEZONE)

# === FSM состояния ===
class Form(StatesGroup):
    waiting_for_time = State()

class TimingForm(StatesGroup):
    waiting_for_input = State()

# === Вспомогательные функции ===
def parse_time(time_str: str) -> Optional[datetime.time]:
    match = re.match(r'^([0-2]?[0-9]):([0-5][0-9])$', time_str.strip())
    if not match:
        return None
    h, m = int(match.group(1)), int(match.group(2))
    if h > 23:
        return None
    return datetime.strptime(f"{h:02d}:{m:02d}", "%H:%M").time()

# === Обработчики команд ===
@dp.message(Command("start"))
@dp.message(F.text == "Изменить")
async def cmd_start(message: Message, state: FSMContext):
    await message.answer("В какое время напоминать о таблетке? Напиши в формате чч:мм (например, 09:30)")
    await state.set_state(Form.waiting_for_time)

@dp.message(Form.waiting_for_time)
async def process_time(message: Message, state: FSMContext):
    time_obj = parse_time(message.text)
    if not time_obj:
        await message.answer("Неверный формат. Попробуй ещё раз: чч:мм")
        return

    user_id = message.from_user.id
    time_str = time_obj.strftime("%H:%M")
    await set_reminder_time(user_id, time_str)

    # Удаляем старые задачи
    for job in scheduler_global.get_jobs():
        if job.kwargs.get("user_id") == user_id:
            job.remove()

    # Добавляем ежедневную задачу
    scheduler_global.add_job(
        send_pill_reminder,
        'cron',
        hour=time_obj.hour,
        minute=time_obj.minute,
        kwargs={'bot': bot, 'user_id': user_id},
        id=f"reminder_{user_id}",
        replace_existing=True
    )

    await message.answer(f"Отлично! Теперь я буду напоминать тебе каждый день в {time_str}.")
    await state.clear()

@dp.message(Command("help"))
async def cmd_help(message: Message):
    await message.answer(
        "Напоминание - Проверка = НП\n"
        "Проверка - Проверка (Реакция) = НПР\n"
        "Проверка - Проверка (Кнопка \"Нет\") = НПН\n\n"
        "Команды:\n"
        "• Расписание мм.гг\n"
        "• Изменить\n"
        "• Покажи тайминги\n"
        "• Исправь тайминги"
    )

@dp.message(F.text == "Покажи тайминги")
async def show_timings(message: Message):
    timings = await get_user_timings(message.from_user.id)
    np_min = timings["np"] // 60
    npr_min = timings["npr"] // 60
    npn_min = timings["npn"] // 60
    await message.answer(
        f"Напоминание → Проверка: {np_min} мин\n"
        f"Проверка → Проверка (без реакции): {npr_min} мин\n"
        f"Проверка → Проверка (после «Нет»): {npn_min} мин"
    )

@dp.message(F.text == "Исправь тайминги")
async def edit_timings_start(message: Message, state: FSMContext):
    await message.answer(
        'Введите тайминги в формате:\n'
        'НП=1800, НПР=300, НПН=1800\n'
        '(значения в секундах)'
    )
    await state.set_state(TimingForm.waiting_for_input)

@dp.message(TimingForm.waiting_for_input)
async def process_timing_input(message: Message, state: FSMContext):
    user_id = message.from_user.id
    text = message.text.strip()
    updates = {}
    try:
        for part in text.split(','):
            part = part.strip()
            if '=' not in part:
                continue
            key, val = part.split('=', 1)
            key = key.strip().upper()
            val = int(val.strip())
            if key == "НП":
                updates["np"] = val
            elif key == "НПР":
                updates["npr"] = val
            elif key == "НПН":
                updates["npn"] = val
            else:
                raise ValueError(f"Неизвестный ключ: {key}")

        if not updates:
            raise ValueError("Нет корректных значений")

        for k, v in updates.items():
            await update_timing(user_id, k, v)

        await message.answer("✅ Тайминги обновлены!")
    except Exception as e:
        await message.answer(f"❌ Ошибка: {e}. Попробуй ещё раз.")
    finally:
        await state.clear()

@dp.message(F.text.regexp(r"^Расписание\s+(\d{2})\.(\d{2})$"))
async def cmd_schedule(message: Message):
    match = re.match(r"^Расписание\s+(\d{2})\.(\d{2})$", message.text)
    if not match:
        await message.answer("Неверный формат. Пример: Расписание 10.25")
        return
    mm, yy = match.group(1), match.group(2)
    month_key = f"{mm}.{yy}"
    logs = await get_logs_for_month(message.from_user.id, month_key)

    if not logs:
        await message.answer(f"Нет записей за {month_key}.")
        return

    text = f"Расписание за {month_key}:\n\n"
    for date, status, time_taken in logs:
        if status == "taken":
            text += f"✅ {date} — выпила в {time_taken}\n"
        elif status == "not_needed":
            text += f"⏸ {date} — пить не нужно\n"
        else:
            text += f"❌ {date} — пропущено\n"
    await message.answer(text)

# === Callback-обработчики ===
@dp.callback_query(F.data == "yes")
async def cb_yes(callback: CallbackQuery):
    user_id = callback.from_user.id
    now = datetime.now().strftime("%H:%M")
    await log_pill(user_id, "taken", now)
    await callback.message.edit_text("Отлично! ✅")
    await cancel_all_jobs(user_id)

@dp.callback_query(F.data == "no")
async def cb_no(callback: CallbackQuery):
    user_id = callback.from_user.id
    await callback.message.edit_text("Напомню снова через некоторое время.")
    await cancel_all_jobs(user_id)

    timings = await get_user_timings(user_id)
    delay_sec = timings["npn"]  # НПН — после нажатия "Нет"

    job_id = f"retry_{user_id}"
    scheduler_global.add_job(
        send_check_message,
        'date',
        run_date=datetime.now() + timedelta(seconds=delay_sec),
        kwargs={'bot': bot, 'user_id': user_id},
        id=job_id,
        replace_existing=True
    )

@dp.callback_query(F.data == "skip_today")
async def cb_skip(callback: CallbackQuery):
    user_id = callback.from_user.id
    await log_pill(user_id, "not_needed")
    await callback.message.edit_text("Хорошо, до завтра.")
    await cancel_all_jobs(user_id)

# === Запуск ===
async def main():
    await init_db()
    from scheduler import set_global_scheduler
    set_global_scheduler(scheduler_global)  # ← связываем планировщик
    scheduler_global.start()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())