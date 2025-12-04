import asyncio
import os
import sys
import re
from urllib.parse import urlparse
from datetime import datetime

# ====== فیکس nest_asyncio ======
try:
    import nest_asyncio
    nest_asyncio.apply()
    print("nest_asyncio اعمال شد")
except ImportError:
    print("nest_asyncio نبود، دارم نصب می‌کنم...")
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "nest_asyncio", "--quiet"])
    import nest_asyncio
    nest_asyncio.apply()
    print("nest_asyncio نصب و اعمال شد!")

# برای سرورهای لجباز (Railway, Render, Fly.io)
if any(x in os.environ for x in ["RAILWAY_STATIC_URL", "RENDER", "FLY_APP_NAME"]):
    asyncio.set_event_loop_policy(asyncio.DefaultEventLoopPolicy())

# ====================== کتابخانه‌ها ======================
import jdatetime
import psycopg2
from psycopg2.extras import RealDictCursor
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    ConversationHandler, MessageHandler, filters, ContextTypes
)

# ====================== متغیرها ======================
TOKEN = os.getenv("TOKEN")
DATABASE_URL = os.getenv("DATABASE_URL")
ADMIN_CHAT_ID = int(os.getenv("ADMIN_CHAT_ID", "7548579249"))
MEET_LINK = "https://meet.google.com/abc-defg-hij"

AVAILABLE_TIMES = {
    "شنبه":     ["10:00", "11:30", "14:00", "15:30", "17:00", "18:30"],
    "یکشنبه":   ["10:00", "11:30", "14:00", "15:30", "17:00", "18:30"],
    "دوشنبه":   ["10:00", "11:30", "14:00", "15:30", "17:00"],
    "سه‌شنبه": ["10:00", "11:30", "14:00", "15:30", "17:00", "18:30"],
    "چهارشنبه": ["10:00", "11:30", "14:00", "15:30", "17:00"],
    "پنج‌شنبه": ["10:00", "11:30", "14:00"],
    "جمعه":     [],
}

NAME, PHONE, AGE, ISSUE, CALENDAR, TIME = range(6)
_memory_appointments = {}
_conn = None
_cursor = None

# ====================== توابع ======================
def get_persian_weekday(jdate):
    weekdays_fa = ["دوشنبه", "سه‌شنبه", "چهارشنبه", "پنج‌شنبه", "جمعه", "شنبه", "یکشنبه"]
    return weekdays_fa[jdate.weekday()]

# ====================== دیتابیس ======================
async def db_connect():
    global _conn, _cursor
    if not DATABASE_URL:
        print("DATABASE_URL تنظیم نشده — از حافظه موقت استفاده می‌شه")
        return
    try:
        url = urlparse(DATABASE_URL)
        _conn = psycopg2.connect(
            dbname=url.path[1:],
            user=url.username,
            password=url.password,
            host=url.hostname,
            port=url.port or 5432,
            cursor_factory=RealDictCursor,
        )
        _cursor = _conn.cursor()
        _cursor.execute("""
            CREATE TABLE IF NOT EXISTS appointments (
                id SERIAL PRIMARY KEY,
                chat_id BIGINT UNIQUE,
                name TEXT,
                phone TEXT,
                age INTEGER,
                issue TEXT,
                date TEXT,
                jalali_date TEXT,
                weekday TEXT,
                time TEXT,
                link TEXT,
                psych TEXT
            );
        """)
        _conn.commit()
        print("دیتابیس متصل شد")
    except Exception as e:
        print("خطا در اتصال دیتابیس:", e)
        _conn = _cursor = None

async def db_execute(query, params=None, fetch=False):
    if not _conn or not _cursor:
        return None
    loop = asyncio.get_running_loop()
    def run():
        try:
            _cursor.execute(query, params or ())
            if fetch:
                return _cursor.fetchall()
            _conn.commit()
        except Exception as e:
            print("خطای دیتابیس:", e)
            _conn.rollback()
    return await loop.run_in_executor(None, run)

# ====================== اعتبارسنجی ======================
PERSIAN_TO_EN = str.maketrans("۰۱۲۳۴۵۶۷۸۹", "0123456789")
def normalize_digits(text: str) -> str:
    return text.translate(PERSIAN_TO_EN)

def valid_name(text: str) -> bool:
    return bool(text.strip()) and not re.search(r"\d", text.strip())

def valid_phone(text: str) -> bool:
    digits = re.sub(r"\D", "", normalize_digits(text))
    return len(digits) in (10, 11)

def valid_age(text: str) -> bool:
    digits = normalize_digits(text).strip()
    return digits.isdigit() and 1 <= int(digits) <= 120

# ====================== کیبوردها ======================
def render_month_keyboard(year: int, month: int):
    first_day = jdatetime.date(year, month, 1)
    days_in_month = jdatetime.j_days_in_month[month - 1]
    start_offset = (first_day.weekday() + 2) % 7
    buttons = []
    buttons.append([
        InlineKeyboardButton("◀️", callback_data=f"cal:prev:{year}:{month}"),
        InlineKeyboardButton(f"{first_day.j_months_fa[month-1]} {year}", callback_data="noop"),
        InlineKeyboardButton("▶️", callback_data=f"cal:next:{year}:{month}"),
    ])
    buttons.append([InlineKeyboardButton(d, callback_data="noop") for d in ["ش", "ی", "د", "س", "چ", "پ", "ج"]])
    week = [None] * 7
    day = 1
    for i in range(start_offset, 7):
        week[i] = day
        day += 1
    buttons.append([InlineKeyboardButton(" " if d is None else str(d),
                                         callback_data="noop" if d is None else f"cal:day:{year}:{month:02d}:{d:02d}") for d in week])
    while day <= days_in_month:
        week = []
        for _ in range(7):
            if day <= days_in_month:
                week.append(day)
                day += 1
            else:
                week.append(None)
        buttons.append([InlineKeyboardButton(" " if d is None else str(d),
                                             callback_data="noop" if d is None else f"cal:day:{year}:{month:02d}:{d:02d}") for d in week])
    buttons.append([
        InlineKeyboardButton("امروز", callback_data="cal:today"),
        InlineKeyboardButton("بستن", callback_data="cal:close"),
    ])
    return InlineKeyboardMarkup(buttons)

def main_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("رزرو جدید", callback_data="menu:new")],
        [InlineKeyboardButton("مشاهده رزرو", callback_data="menu:view"),
         InlineKeyboardButton("ویرایش اطلاعات", callback_data="menu:edit")],
        [InlineKeyboardButton("انصراف (حذف رزرو)", callback_data="menu:cancel")],
    ])

# ====================== هندلرها ======================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = "سلام! به ربات رزرو مشاوره روانشناسی خوش آمدید\nلطفاً از منوی زیر استفاده کنید:"
    if update.message:
        await update.message.reply_text(text, reply_markup=main_menu())
    else:
        await update.callback_query.edit_message_text(text, reply_markup=main_menu())

# ... (بقیه هندلرهای menu_handler, edit_handler, name, phone, age, issue, calendar_handler, time_handler, cancel همانند نسخه‌ی قبلی بدون تغییر) ...

# ====================== اجرا ======================
async def main():
    await db_connect()
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(edit_handler, pattern="^edit:"))
    app.add_handler(ConversationHandler(
        entry_points=[CallbackQueryHandler(menu_handler, pattern="^menu:")],
        states={
            NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, name)],
            PHONE: [MessageHandler(filters.TEXT & ~filters.COMMAND, phone)],
            AGE: [MessageHandler(filters.TEXT & ~filters.COMMAND, age)],
            ISSUE: [MessageHandler(filters.TEXT & ~filters.COMMAND, issue)],
            CALENDAR: [CallbackQueryHandler(calendar_handler, pattern="^cal:")],
            TIME: [CallbackQueryHandler(time_handler, pattern="^time:")],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    ))
    print("ربات داره استارت می‌خوره... عشقم این دفعه حتماً کار می‌کنه!")
    await app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    asyncio.run(main())
