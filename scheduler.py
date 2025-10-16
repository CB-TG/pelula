from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
import asyncio
from datetime import datetime
from aiogram import Bot
from database import get_reminder_time

class ReminderScheduler:
    def __init__(self, bot: Bot):
        self.bot = bot
        self.scheduler = AsyncIOScheduler()
        self.active_jobs = {}  # user_id -> job_id
        self.active_queries = {}  # user_id -> (message_id, task)

    async def start_scheduler(self):
        self.scheduler.start()

    async def schedule_reminder(self, user_id: int):
        time_str = await get_reminder_time(user_id)
        if not time_str:
            return
        hour, minute = map(int, time_str.split(":"))
        job_id = f"reminder_{user_id}"
        if job_id in self.active_jobs:
            self.scheduler.remove_job(job_id)
        self.scheduler.add_job(
            self.send_reminder,
            CronTrigger(hour=hour, minute=minute),
            id=job_id,
            args=[user_id],
            replace_existing=True
        )
        self.active_jobs[job_id] = user_id

    async def send_reminder(self, user_id: int):
        from main import get_or_create_user_data, save_user_data
        data = get_or_create_user_data(user_id)
        if data.get("skip_today", False):
            data["skip_today"] = False
            save_user_data(user_id, data)
            return

        from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Сегодня не нужно", callback_data="skip_today")],
            [InlineKeyboardButton(text="Да", callback_data="taken"),
             InlineKeyboardButton(text="Нет", callback_data="not_taken")]
        ])
        msg = await self.bot.send_message(user_id, "Пора выпить таблетку!")
        data["reminder_message_id"] = msg.message_id
        save_user_data(user_id, data)
        # Через 30 мин отправить вопрос
        self.scheduler.add_job(
            self.ask_if_taken,
            'date',
            run_date=datetime.now().replace(minute=datetime.now().minute + 30, second=0, microsecond=0),
            args=[user_id],
            id=f"ask_{user_id}"
        )

    async def ask_if_taken(self, user_id: int):
        from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Сегодня не нужно", callback_data="skip_today")],
            [InlineKeyboardButton(text="Да", callback_data="taken"),
             InlineKeyboardButton(text="Нет", callback_data="not_taken")]
        ])
        msg = await self.bot.send_message(user_id, "Ты выпила таблетку?", reply_markup=keyboard)
        from main import get_or_create_user_data, save_user_data
        data = get_or_create_user_data(user_id)
        data["question_message_id"] = msg.message_id
        save_user_data(user_id, data)
        # Запускаем цикл повтора
        self.start_repeat_query(user_id)

    def start_repeat_query(self, user_id: int):
        from main import get_or_create_user_data, save_user_data
        data = get_or_create_user_data(user_id)
        task = asyncio.create_task(self.repeat_message(user_id))
        data["repeat_task"] = task
        save_user_data(user_id, data)

    async def repeat_message(self, user_id: int):
        while True:
            from main import get_or_create_user_data
            data = get_or_create_user_data(user_id)
            if "repeat_task" not in data:
                break
            msg_id = data.get("question_message_id")
            if msg_id:
                try:
                    await self.bot.delete_message(user_id, msg_id)
                except Exception:
                    pass
            from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="Сегодня не нужно", callback_data="skip_today")],
                [InlineKeyboardButton(text="Да", callback_data="taken"),
                 InlineKeyboardButton(text="Нет", callback_data="not_taken")]
            ])
            new_msg = await self.bot.send_message(user_id, "Ты выпила таблетку?", reply_markup=keyboard)
            data["question_message_id"] = new_msg.message_id
            await asyncio.sleep(300)  # 5 минут