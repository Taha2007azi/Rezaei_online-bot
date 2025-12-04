# bot.py
import os
import re
import asyncio
from urllib.parse import urlparse
from datetime import datetime

import jdatetime
import psycopg2
from psycopg2.extras import RealDictCursor

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup
)
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ConversationHandler,
    MessageHandler,
    filters,
    ContextTypes
)

# -------------------------
# Configuration / Globals
# -------------------------
TOKEN = os.getenv("TOKEN")
DATABASE_URL = os.getenv("DATABASE_URL")  # optional, recommended
ADMIN_CHAT_ID = int(os.getenv("ADMIN_CHAT_ID", "7548579249"))

# Fixed Google Meet link (requested: ثابت باشد)
MEET_LINK = "https://meet.google.com/new"

# Conversation states
NAME, PHONE, AGE, ISSUE, CALENDAR, TIME = range(6)

# In-memory fallback storage if DB unavailable
_memory_users = {}       # chat_id -> {name, phone, age}
_memory_appointments = {}  # chat_id -> appointment dict

# DB connection holder
_conn = None
_cursor = None

# -------------------------
# Utility: DB safe wrappers
# -------------------------
async def db_connect():
    global _conn, _cursor
    if DATABASE_URL is None:
        print("DATABASE_URL not provided — running in memory-only mode.")
        _conn = None
        _cursor = None
        return

    try:
        url = urlparse(DATABASE_URL)
        _conn = psycopg2.connect(
            dbname=url.path[1:],
            user=url.username,
            password=url.password,
            host=url.hostname,
            port=url.port,
            cursor_factory=RealDictCursor
        )
        _cursor = _conn.cursor()
        # ensure tables
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
        print("Postgres connected and table ready.")
    except Exception as e:
        print("Postgres connection error:", e)
        _conn = None
        _cursor = None

async def db_execute(query, params=None, fetch=False):
    """Run blocking DB ops in executor."""
    if _conn is None or _cursor is None:
        return None
    loop = asyncio.get_running_loop()
    def run():
        try:
            _cursor.execute(query, params or ())
            if fetch:
                return _cursor.fetchall()
            _conn.commit()
            return None
        except Exception as e:
            print("DB exec error:", e)
            return None
    return await loop.run_in_executor(None, run)

# -------------------------
# Validation helpers
# -------------------------
PERSIAN_TO_EN_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹", "0123456789")

def normalize_digits(s: str) -> str:
    return s.translate(PERSIAN_TO_EN_DIGITS)

def valid_phone(s: str) -> bool:
    s2 = re.sub(r"\D", "", normalize_digits(s))
    return len(s2) in (10, 11)

def valid_age(s: str) -> bool:
    s2 = normalize_digits(s).strip()
    return s2.isdigit() and 1 <= int(s2) <= 120

def valid_name(s: str) -> bool:
    # allow Persian/Latin letters and spaces, disallow digits
    s = s.strip()
    if not s:
        return False
    return not bool(re.search(r"\d", s))

# -------------------------
# Jalali calendar helpers
# -------------------------
def jalali_month_calendar(year: int, month: int):
    """Return list of weeks; each week is list of day numbers or None (to fill)."""
    first = jdatetime.date(year, month, 1)
    days_in_month = jdatetime.j_days_in_month[month - 1]
    # jdatetime weekday: 0=Mon? Actually jdatetime.date.weekday() returns 0=Mon; we want Sh,Ya... but we'll map
    # We'll use weekday where Saturday is 5? To keep calendar starting Saturday we map accordingly.
    # We'll compute weekday index where Saturday=0 ... Friday=6
    def jalali_weekday(jd):
        # jd.weekday(): Monday=0 ... Sunday=6
        # Persian week start Saturday. Saturday index should be 0.
        # Calculate weekday number from Saturday:
        # Monday(0) -> index = (0+2) % 7 = 2 -> Monday is 2
        return (jd.weekday() + 2) % 7

    first_w = jalali_weekday(first)
    weeks = []
    week = [None]*7
    day = 1
    # fill first week
    for i in range(first_w, 7):
        week[i] = day
        day += 1
    weeks.append(week)
    while day <= days_in_month:
        week = [None]*7
        for i in range(7):
            if day <= days_in_month:
                week[i] = day
                day += 1
        weeks.append(week)
    return weeks

def render_month_keyboard(year: int, month: int, ctx_prefix="cal"):
    """Return InlineKeyboardMarkup for jalali month with navigation."""
    weeks = jalali_month_calendar(year, month)
    buttons = []
    # header: month-year with prev/next
    header = [
        InlineKeyboardButton("◀️", callback_data=f"{ctx_prefix}:month_prev:{year}:{month}"),
        InlineKeyboardButton(f"{jdatetime.date(year, month, 1).j_months_fa[month-1]} {year}", callback_data="noop"),
        InlineKeyboardButton("▶️", callback_data=f"{ctx_prefix}:month_next:{year}:{month}"),
    ]
    buttons.append(header)
    # weekdays row (Sat..Fri)
    days_row = ["ش", "ی", "د", "س", "چ", "پ", "ج"]  # Saturday .. Friday initial letters
    buttons.append([InlineKeyboardButton(d, callback_data="noop") for d in days_row])
    # weeks
    for w in weeks:
        row = []
        for d in w:
            if d is None:
                row.append(InlineKeyboardButton(" ", callback_data="noop"))
            else:
                # format callback data: cal:day:YYYY:MM:DD
                yyyy = year
                mm = month
                dd = d
                callback = f"{ctx_prefix}:day:{yyyy}:{mm:02d}:{dd:02d}"
                row.append(InlineKeyboardButton(str(d), callback_data=callback))
        buttons.append(row)
    # bottom: today and close
    buttons.append([
        InlineKeyboardButton("امروز", callback_data=f"{ctx_prefix}:today"),
        InlineKeyboardButton("بستن", callback_data=f"{ctx_prefix}:close")
    ])
    return InlineKeyboardMarkup(buttons)

# -------------------------
# Main menu (Inline)
# -------------------------
def main_menu_markup():
    keyboard = [
        [InlineKeyboardButton("🎯 رزرو جدید", callback_data="menu:new")],
        [InlineKeyboardButton("📋 مشاهده رزرو", callback_data="menu:view"),
         InlineKeyboardButton("✏️ ویرایش اطلاعات", callback_data="menu:edit")],
        [InlineKeyboardButton("❌ انصراف (حذف رزرو)", callback_data="menu:cancel")]
    ]
    return InlineKeyboardMarkup(keyboard)

# -------------------------
# Handlers
# -------------------------
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # send or edit main menu
    if update.message:
        await update.message.reply_text("سلام! برای مدیریت نوبت‌ها از پنجرهٔ زیر استفاده کنید:", reply_markup=main_menu_markup())
    elif update.callback_query:
        await update.callback_query.edit_message_text("منوی اصلی:", reply_markup=main_menu_markup())

# Menu callback entry
async def callback_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    data = q.data  # e.g., "menu:new"
    chat_id = q.message.chat_id
    if data == "menu:new":
        # start reservation flow: ask name (or reuse stored if exists)
        # try to load user
        user = None
        if _cursor:
            rows = await db_execute("SELECT name, phone, age FROM appointments WHERE chat_id=%s", (chat_id,), fetch=True)
            # here appointments table stores the active appointment; if none, try users fallback
            if rows:
                # pick first
                user = rows[0]
        else:
            user = _memory_users.get(chat_id)
        if user and user.get("name"):
            # prefill and jump to next? to keep flow consistent, we'll still ask name to confirm
            await q.edit_message_text(f"نام شما در سیستم: {user.get('name')}\nاگر می‌خواهی تغییر بدی، نام جدید را وارد کن. در غیر این صورت دوباره نام را ارسال کن یا ادامه بده.", reply_markup=None)
            return NAME
        else:
            await q.edit_message_text("لطفاً نام و نام خانوادگی خود را وارد کنید:", reply_markup=None)
            return NAME

    elif data == "menu:view":
        # show appointment info
        info = None
        if _cursor:
            rows = await db_execute("SELECT * FROM appointments WHERE chat_id=%s", (chat_id,), fetch=True)
            if rows:
                info = rows[0]
        else:
            info = _memory_appointments.get(chat_id)
        if not info:
            await q.edit_message_text("شما رزروی ثبت نکرده‌اید.", reply_markup=main_menu_markup())
            return ConversationHandler.END
        # build message
        msg = (
            f"📌 اطلاعات رزرو شما:\n\n"
            f"نام: {info.get('name')}\n"
            f"شماره: {info.get('phone')}\n"
            f"سن: {info.get('age')}\n"
            f"روانشناس: {info.get('psych')}\n"
            f"تاریخ (شمسی): {info.get('jalali_date')} — {info.get('weekday')}\n"
            f"ساعت: {info.get('time')}\n"
            f"لینک جلسه: {info.get('link')}\n"
        )
        await q.edit_message_text(msg, reply_markup=main_menu_markup())
        return ConversationHandler.END

    elif data == "menu:edit":
        # present options via inline
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("تغییر نام", callback_data="edit:name")],
            [InlineKeyboardButton("تغییر شماره", callback_data="edit:phone")],
            [InlineKeyboardButton("تغییر سن", callback_data="edit:age")],
            [InlineKeyboardButton("بازگشت", callback_data="menu:back")]
        ])
        await q.edit_message_text("کدام مورد را می‌خواهید تغییر دهید؟", reply_markup=kb)
        return ConversationHandler.END

    elif data == "menu:cancel":
        # delete appointment
        if _cursor:
            await db_execute("DELETE FROM appointments WHERE chat_id=%s", (chat_id,))
        else:
            _memory_appointments.pop(chat_id, None)
        await q.edit_message_text("رزرو (در صورت وجود) حذف شد.", reply_markup=main_menu_markup())
        return ConversationHandler.END

    elif data == "menu:back":
        await q.edit_message_text("منوی اصلی:", reply_markup=main_menu_markup())
        return ConversationHandler.END

    else:
        # unknown
        await q.edit_message_text("گزینهٔ نامشخص.", reply_markup=main_menu_markup())
        return ConversationHandler.END

# Edit sub-callbacks
async def callback_edit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    data = q.data  # edit:name / edit:phone / edit:age
    if data == "edit:name":
        await q.edit_message_text("لطفاً نام جدید را ارسال کنید:")
        return NAME
    elif data == "edit:phone":
        await q.edit_message_text("لطفاً شماره جدید را ارسال کنید:")
        return PHONE
    elif data == "edit:age":
        await q.edit_message_text("لطفاً سن جدید را ارسال کنید:")
        return AGE
    else:
        await q.edit_message_text("بازگشت", reply_markup=main_menu_markup())
        return ConversationHandler.END

# Name handler
async def name_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    chat_id = update.message.chat_id
    if not valid_name(text):
        await update.message.reply_text("نام معتبر نیست — فقط حروف و فاصله مجاز است. دوباره وارد کنید:")
        return NAME
    context.user_data['name'] = text
    # save temporarily in memory; DB save happens when appointment created or on edits
    _memory_users.setdefault(chat_id, {})['name'] = text
    await update.message.reply_text("نام ثبت شد. لطفاً شماره تلفن (10 یا 11 رقم) را وارد کنید:")
    return PHONE

# Phone handler
async def phone_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    chat_id = update.message.chat_id
    if not valid_phone(text):
        await update.message.reply_text("شماره تلفن معتبر نیست — فقط 10 یا 11 رقم. دوباره وارد کنید:")
        return PHONE
    norm = re.sub(r"\D", "", normalize_digits(text))
    context.user_data['phone'] = norm
    _memory_users.setdefault(chat_id, {})['phone'] = norm
    await update.message.reply_text("شماره ثبت شد. لطفاً سن خود را به عدد وارد کنید:")
    return AGE

# Age handler
async def age_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    chat_id = update.message.chat_id
    if not valid_age(text):
        await update.message.reply_text("سن معتبر نیست — لطفاً عددی بین 1 تا 120 وارد کنید:")
        return AGE
    age_num = int(normalize_digits(text))
    context.user_data['age'] = age_num
    _memory_users.setdefault(chat_id, {})['age'] = age_num

    # After we have name/phone/age, proceed to issue then calendar
    await update.message.reply_text("موضوع جلسه را توضیح دهید (اختیاری):")
    return ISSUE

async def issue_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['issue'] = update.message.text.strip()
    # show calendar for current jalali month
    today = jdatetime.date.today()
    markup = render_month_keyboard(today.year, today.month, ctx_prefix="cal")
    await update.message.reply_text("لطفاً روز مورد نظر را انتخاب کنید:", reply_markup=markup)
    return CALENDAR

# Calendar callbacks (prefix cal)
async def callback_calendar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    data = q.data  # e.g. cal:day:YYYY:MM:DD or cal:month_next:YYYY:MM
    parts = data.split(":")
    if len(parts) < 2:
        await q.edit_message_text("خطای داخلی تقویم.", reply_markup=main_menu_markup())
        return ConversationHandler.END
    action = parts[1]
    if action == "day":
        _, _, y, m, d = parts
        y = int(y); m = int(m); d = int(d)
        # store selected jalali date
        jalali_str = f"{y}/{m:02d}/{d:02d}"
        context.user_data['jalali_date'] = jalali_str
        weekday = ["شنبه","یکشنبه","دوشنبه","سه‌شنبه","چهارشنبه","پنج‌شنبه","جمعه"][jdatetime.datetime.strptime(jalali_str, "%Y/%m/%d").date().weekday()]
        context.user_data['weekday'] = weekday
        # Now show available times for that weekday
        available = AVAILABLE_TIMES.get(weekday, [])
        # filter by existing bookings on that jalali date
        booked = []
        if _cursor:
            rows = await db_execute("SELECT time FROM appointments WHERE jalali_date=%s", (jalali_str,), fetch=True)
            if rows:
                booked = [r['time'] for r in rows]
        else:
            # in-memory
            for v in _memory_appointments.values():
                if v.get('jalali_date') == jalali_str:
                    booked.append(v.get('time'))
        free = [t for t in available if t not in booked]
        if not free:
            await q.edit_message_text("متاسفانه این روز ظرفیت تکمیل است.", reply_markup=main_menu_markup())
            return ConversationHandler.END
        kb = InlineKeyboardMarkup([[InlineKeyboardButton(t, callback_data=f"time:{t}")] for t in free])
        await q.edit_message_text("لطفاً ساعت را انتخاب کنید:", reply_markup=kb)
        return TIME

    elif action in ("month_next", "month_prev"):
        _, _, y, m = parts
        y = int(y); m = int(m)
        # compute next or prev month in jalali
        if action == "month_next":
            # increment month
            if m == 12:
                y += 1; m = 1
            else:
                m += 1
        else:
            if m == 1:
                y -= 1; m = 12
            else:
                m -= 1
        markup = render_month_keyboard(y, m, ctx_prefix="cal")
        await q.edit_message_text("انتخاب روز:", reply_markup=markup)
        return CALENDAR

    elif action == "today":
        t = jdatetime.date.today()
        markup = render_month_keyboard(t.year, t.month, ctx_prefix="cal")
        await q.edit_message_text("انتخاب روز:", reply_markup=markup)
        return CALENDAR

    elif action == "close":
        await q.edit_message_text("عملیات لغو شد.", reply_markup=main_menu_markup())
        return ConversationHandler.END

    else:
        await q.edit_message_text("عملیات نامشخص.", reply_markup=main_menu_markup())
        return ConversationHandler.END

# Time callback
async def callback_time(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    data = q.data  # time:HH:MM
    chat_id = q.message.chat_id
    if not data.startswith("time:"):
        await q.edit_message_text("خطا در انتخاب ساعت.", reply_markup=main_menu_markup())
        return ConversationHandler.END
    time_selected = data.split(":", 1)[1]
    # gather user data
    name = context.user_data.get('name') or _memory_users.get(chat_id, {}).get('name')
    phone = context.user_data.get('phone') or _memory_users.get(chat_id, {}).get('phone')
    age = context.user_data.get('age') or _memory_users.get(chat_id, {}).get('age')
    issue = context.user_data.get('issue', "")
    jalali_date = context.user_data.get('jalali_date')
    weekday = context.user_data.get('weekday')
    if not (name and phone and age and jalali_date):
        await q.edit_message_text("اطلاعات ناقص است. دوباره از منو شروع کنید.", reply_markup=main_menu_markup())
        return ConversationHandler.END

    # remove any previous appointment of this chat (single active appointment per user)
    if _cursor:
        await db_execute("DELETE FROM appointments WHERE chat_id=%s", (chat_id,))
        await db_execute(
            "INSERT INTO appointments (chat_id,name,phone,age,issue,date,jalali_date,weekday,time,link,psych) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
            (chat_id, name, phone, age, issue, datetime.utcnow().isoformat(), jalali_date, weekday, time_selected, MEET_LINK, "دکتر رضائی")
        )
    else:
        _memory_appointments[chat_id] = {
            "chat_id": chat_id,
            "name": name,
            "phone": phone,
            "age": age,
            "issue": issue,
            "date": datetime.utcnow().isoformat(),
            "jalali_date": jalali_date,
            "weekday": weekday,
            "time": time_selected,
            "link": MEET_LINK,
            "psych": "دکتر رضائی"
        }

    # notify admin
    try:
        await context.bot.send_message(ADMIN_CHAT_ID, f"رزرو جدید:\nنام: {name}\nشماره: {phone}\nسن: {age}\nتاریخ: {jalali_date} ({weekday})\nساعت: {time_selected}\nلینک: {MEET_LINK}")
    except Exception as e:
        print("Failed to notify admin:", e)

    await q.edit_message_text(f"رزرو شما ثبت شد ✅\n\nتاریخ: {jalali_date} ({weekday})\nساعت: {time_selected}\nلینک: {MEET_LINK}", reply_markup=main_menu_markup())
    return ConversationHandler.END

# Fallback cancel
async def fallback_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message:
        await update.message.reply_text("عملیات کنسل شد.", reply_markup=main_menu_markup())
    elif update.callback_query:
        await update.callback_query.edit_message_text("عملیات کنسل شد.", reply_markup=main_menu_markup())
    return ConversationHandler.END

# -------------------------
# Setup application & handlers
# -------------------------
async def main():
    # connect to db
    await db_connect()

    app = Application.builder().token(TOKEN).build()

    # Conversation for main flows: NAME -> PHONE -> AGE -> ISSUE -> CALENDAR -> TIME
    conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(callback_menu, pattern="^menu:")],
        states={
            NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, name_handler)],
            PHONE: [MessageHandler(filters.TEXT & ~filters.COMMAND, phone_handler)],
            AGE: [MessageHandler(filters.TEXT & ~filters.COMMAND, age_handler)],
            ISSUE: [MessageHandler(filters.TEXT & ~filters.COMMAND, issue_handler)],
            CALENDAR: [CallbackQueryHandler(callback_calendar, pattern="^cal:")],
            TIME: [CallbackQueryHandler(callback_time, pattern="^time:")]
        },
        fallbacks=[CommandHandler("cancel", fallback_cancel)]
    )

    app.add_handler(conv)
    # Entry: /start shows the main menu
    app.add_handler(CommandHandler("start", cmd_start))
    # top-level menu callback
    app.add_handler(CallbackQueryHandler(callback_menu, pattern="^menu:"))
    # edit sub callbacks
    app.add_handler(CallbackQueryHandler(callback_edit, pattern="^edit:"))

    print("Bot started (polling)...")
    await app.run_polling()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Bot stopped by user.")
