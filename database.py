# database.py
import aiosqlite
from datetime import datetime

DB_PATH = "data.db"

# Значения по умолчанию (в секундах)
DEFAULT_NP = 1800   # Напоминание → Проверка
DEFAULT_NPR = 300   # Проверка → Повтор без реакции
DEFAULT_NPN = 1800  # Проверка → Повтор после "Нет"

async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        # Обновляем таблицу users, добавляем колонку pills_left
        # SQLite не поддерживает DROP COLUMN, но можно добавить
        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                reminder_time TEXT,
                pills_left INTEGER
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                date TEXT,
                status TEXT,
                time_taken TEXT
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                user_id INTEGER PRIMARY KEY,
                np INTEGER,
                npr INTEGER,
                npn INTEGER
            )
        """)
        await db.commit()

# --- Работа с временем напоминания ---
async def set_reminder_time(user_id: int, time_str: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR REPLACE INTO users (user_id, reminder_time) VALUES (?, ?)",
            (user_id, time_str)
        )
        await db.commit()

async def get_reminder_time(user_id: int) -> str | None:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT reminder_time FROM users WHERE user_id = ?", (user_id,)) as cursor:
            row = await cursor.fetchone()
            return row[0] if row else None

# --- Логирование приёма ---
async def log_pill(user_id: int, status: str, time_taken: str | None = None):
    today = datetime.now().strftime("%d.%m.%y")
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO logs (user_id, date, status, time_taken) VALUES (?, ?, ?, ?)",
            (user_id, today, status, time_taken)
        )
        await db.commit()

# --- Получение логов за месяц ---
async def get_logs_for_month(user_id: int, month: str) -> list:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT date, status, time_taken FROM logs WHERE user_id = ? AND date LIKE ? ORDER BY date",
            (user_id, f"%.{month}")
        ) as cursor:
            rows = await cursor.fetchall()
            return rows

# --- Работа с таймингами ---
async def get_user_timings(user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT np, npr, npn FROM settings WHERE user_id = ?", (user_id,)
        ) as cursor:
            row = await cursor.fetchone()
            if row:
                return {"np": row[0], "npr": row[1], "npn": row[2]}
            else:
                # Устанавливаем значения по умолчанию
                await db.execute(
                    "INSERT INTO settings (user_id, np, npr, npn) VALUES (?, ?, ?, ?)",
                    (user_id, DEFAULT_NP, DEFAULT_NPR, DEFAULT_NPN)
                )
                await db.commit()
                return {"np": DEFAULT_NP, "npr": DEFAULT_NPR, "npn": DEFAULT_NPN}

async def update_timing(user_id: int, key: str, value: int):
    async with aiosqlite.connect(DB_PATH) as db:
        # Убедимся, что запись существует
        await get_user_timings(user_id)
        await db.execute(
            f"UPDATE settings SET {key} = ? WHERE user_id = ?",
            (value, user_id)
        )
        await db.commit()

# --- Работа с пачкой таблеток ---
async def create_new_pack(user_id: int, count: int = 21):
    """Создаёт новую пачку на `count` таблеток"""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE users SET pills_left = ? WHERE user_id = ?",
            (count, user_id)
        )
        # Если пользователя нет в таблице, добавим его с reminder_time = NULL
        # Это нужно, чтобы INSERT OR REPLACE в других функциях работал корректно
        # Но можно и обойтись без этого, если пользователь всегда сначала задаёт время
        # Но безопаснее — обновить или вставить
        # Если вдруг user не существует, вставим с reminder_time = NULL
        await db.execute(
            "INSERT OR IGNORE INTO users (user_id, reminder_time) VALUES (?, NULL)",
            (user_id,)
        )
        await db.execute(
            "UPDATE users SET pills_left = ? WHERE user_id = ?",
            (count, user_id)
        )
        await db.commit()

async def get_pills_left(user_id: int) -> int | None:
    """Возвращает остаток таблеток или None, если пачка не активна"""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT pills_left FROM users WHERE user_id = ?", (user_id,)) as cursor:
            row = await cursor.fetchone()
            return row[0] if row and row[0] is not None else None

async def decrement_pill(user_id: int) -> int | None:
    """Уменьшает счётчик на 1 и возвращает новый остаток"""
    async with aiosqlite.connect(DB_PATH) as db:
        # Сначала получим текущее значение
        async with db.execute("SELECT pills_left FROM users WHERE user_id = ?", (user_id,)) as cursor:
            row = await cursor.fetchone()
            if not row or row[0] is None or row[0] <= 0:
                return None  # пачка не активна или закончилась
        new_count = row[0] - 1
        await db.execute(
            "UPDATE users SET pills_left = ? WHERE user_id = ?",
            (new_count, user_id)
        )
        await db.commit()
        return new_count