import aiosqlite
import os

DB_NAME = 'data.db'

async def init_db():
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                reminder_time TEXT
            )
        ''')
        await db.execute('''
            CREATE TABLE IF NOT EXISTS logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                date TEXT,
                status TEXT,
                time_taken TEXT DEFAULT NULL
            )
        ''')
        await db.commit()

async def set_reminder_time(user_id: int, time_str: str):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute('''
            INSERT OR REPLACE INTO users (user_id, reminder_time)
            VALUES (?, ?)
        ''', (user_id, time_str))
        await db.commit()

async def get_reminder_time(user_id: int):
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute('SELECT reminder_time FROM users WHERE user_id = ?', (user_id,))
        row = await cursor.fetchone()
        return row[0] if row else None

async def log_action(user_id: int, date: str, status: str, time_taken: str = None):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute('''
            INSERT INTO logs (user_id, date, status, time_taken)
            VALUES (?, ?, ?, ?)
        ''', (user_id, date, status, time_taken))
        await db.commit()

async def get_logs_for_month(user_id: int, month: str, year: str):
    month_year = f"{year}-{month.zfill(2)}"
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute('''
            SELECT date, status, time_taken FROM logs
            WHERE user_id = ? AND date LIKE ?
            ORDER BY date
        ''', (user_id, f"{month_year}-%"))
        return await cursor.fetchall()