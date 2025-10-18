# scheduler.py
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from aiogram import Bot
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from tzlocal import get_localzone
import asyncio
import logging
from database import get_user_timings

logger = logging.getLogger(__name__)

LOCAL_TZ = ZoneInfo("Europe/Moscow")

active_polling_jobs = {}
active_check_jobs = {}

# Глобальная ссылка на планировщик — будет установлена извне
global_scheduler = None


def set_global_scheduler(scheduler: AsyncIOScheduler):
    global global_scheduler
    global_scheduler = scheduler


def make_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Сегодня не нужно", callback_data="skip_today")],
        [InlineKeyboardButton(text="Да", callback_data="yes"), InlineKeyboardButton(text="Нет", callback_data="no")]
    ])


LOCAL_TZ = get_localzone()


async def send_pill_reminder(bot: Bot, user_id: int):
    await bot.send_message(user_id, "Пора выпить таблетку!")
    timings = await get_user_timings(user_id)
    delay_sec = timings["np"]
    # Используем осознанное время в том же часовом поясе, что и scheduler_global!
    run_time = datetime.now(LOCAL_TZ) + timedelta(seconds=delay_sec)
    if global_scheduler is None:
        logger.error("global_scheduler not set!")
        return
    global_scheduler.add_job(
        send_check_message,
        'date',
        run_date=run_time,
        kwargs={'bot': bot, 'user_id': user_id},
        id=f"check_{user_id}",
        replace_existing=True
    )


async def send_check_message(bot: Bot, user_id: int):
    msg = await bot.send_message(user_id, "Ты выпила таблетку?", reply_markup=make_keyboard())
    # Сохраняем в user_data через bot (без импорта dp!)
    # Но aiogram 3 не даёт прямого доступа к storage извне...
    # Поэтому временно используем in-memory dict
    from bot import user_check_data
    user_check_data[user_id] = {
        "last_check_msg_id": msg.message_id,
        "last_check_chat_id": user_id
    }

    timings = await get_user_timings(user_id)
    interval_sec = timings["npr"]

    scheduler = AsyncIOScheduler(timezone="UTC")
    scheduler.add_job(
        resend_check_message,
        'interval',
        seconds=interval_sec,
        args=[bot, user_id],
        id=f"poll_{user_id}",
        replace_existing=True
    )
    scheduler.start()
    active_polling_jobs[user_id] = scheduler


async def resend_check_message(bot: Bot, user_id: int):
    from bot import user_check_data
    data = user_check_data.get(user_id, {})
    msg_id = data.get("last_check_msg_id")
    chat_id = data.get("last_check_chat_id")
    try:
        if msg_id and chat_id:
            await bot.delete_message(chat_id=chat_id, message_id=msg_id)
    except Exception as e:
        logger.warning(f"Не удалось удалить сообщение: {e}")

    msg = await bot.send_message(user_id, "Ты выпила таблетку?", reply_markup=make_keyboard())
    user_check_data[user_id] = {
        "last_check_msg_id": msg.message_id,
        "last_check_chat_id": user_id
    }


async def cancel_all_jobs(user_id: int):
    if user_id in active_polling_jobs:
        scheduler = active_polling_jobs.pop(user_id)
        scheduler.shutdown(wait=False)
    if user_id in active_check_jobs:
        job_id = active_check_jobs.pop(user_id)
        if global_scheduler and global_scheduler.get_job(job_id):
            global_scheduler.remove_job(job_id)