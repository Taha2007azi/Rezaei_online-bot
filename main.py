from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ConversationHandler, MessageHandler, filters, ContextTypes
import jdatetime
import psycopg2
import os
from urllib.parse import urlparse

# وضعیت‌های مکالمه
MENU, NAME, PHONE, AGE, ISSUE, DATE, TIME, NAME_EDIT, PHONE_EDIT = range(9)

# توکن بات و ادمین
TOKEN = os.getenv('TOKEN')
ADMIN_CHAT_ID = 7548579249

# --- اتصال به PostgreSQL ---
DATABASE_URL = os.getenv("DATABASE_URL") or "postgresql://postgres:dSyLEmnDgGChdXJzygbTMGLNhFYcshtX@interchange.proxy.rlwy.net:52387/railway"
url = urlparse(DATABASE_URL)

conn = psycopg2.connect(
    dbname=url.path[1:],
    user=url.username,
    password=url.password,
    host=url.hostname,
    port=url.port
)
c = conn.cursor()

# ساخت جدول اگر موجود نیست
c.execute('''
CREATE TABLE IF NOT EXISTS appointments (
    id SERIAL PRIMARY KEY,
    name TEXT,
    phone TEXT,
    age INTEGER,
    issue TEXT,
    psych TEXT,
    date TEXT,
    time TEXT,
    link TEXT,
    paid INTEGER
)
''')
conn.commit()

# ساعات کاری روانشناس
PSYCH = "دکتر رضائی"
PSYCH_SCHEDULE = {
    "شنبه": ["10:00","11:00","14:00","15:00","16:00","17:00","18:00"],
    "یکشنبه": ["10:00","11:00","14:00","15:00","16:00","17:00","18:00"],
    "دوشنبه": ["10:00","11:00","14:00","15:00","16:00","17:00"],
    "سه‌شنبه": ["10:00","11:00","14:00","15:00","16:00"],
    "چهارشنبه": ["10:00","11:00","14:00","15:00","16:00","17:00","18:00"]
}

# --- منوی اصلی ---
async def main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("رزرو وقت جدید", callback_data="new_appointment")],
        [InlineKeyboardButton("مشاهده اطلاعات و رزروها", callback_data="view_info")],
        [InlineKeyboardButton("تغییر نام", callback_data="edit_name")],
        [InlineKeyboardButton("تغییر شماره", callback_data="edit_phone")],
        [InlineKeyboardButton("انصراف از رزرو", callback_data="cancel_appointment")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    if update.message:
        await update.message.reply_text("سلام! 👋\nلطفاً یکی از گزینه‌های زیر را انتخاب کنید:", reply_markup=reply_markup)
    elif update.callback_query:
        await update.callback_query.edit_message_text("منوی اصلی:", reply_markup=reply_markup)
    return MENU

# --- مسیر انتخاب منو ---
async def menu_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    choice = query.data

    if choice == "new_appointment":
        await query.edit_message_text(f"رزرو جدید برای {PSYCH}\nلطفاً نام و نام خانوادگی خود را وارد کنید:")
        return NAME
    elif choice == "view_info":
        phone = context.user_data.get("phone")
        if not phone:
            await query.edit_message_text("ابتدا یک رزرو ثبت کنید یا شماره خود را وارد کنید.")
            return MENU
        c.execute("SELECT date, time, psych FROM appointments WHERE phone = %s", (phone,))
        rows = c.fetchall()
        if rows:
            msg = "\n".join([f"{psych} - {date} ساعت {time}" for date, time, psych in rows])
        else:
            msg = "رزروی ثبت نشده است."
        await query.edit_message_text(f"رزروهای شما:\n{msg}")
        return MENU
    elif choice == "edit_name":
        await query.edit_message_text("نام جدید خود را وارد کنید:")
        return NAME_EDIT
    elif choice == "edit_phone":
        await query.edit_message_text("شماره جدید خود را وارد کنید:")
        return PHONE_EDIT
    elif choice == "cancel_appointment":
        phone = context.user_data.get("phone")
        if not phone:
            await query.edit_message_text("رزوی ثبت نشده است.")
            return MENU
        c.execute("DELETE FROM appointments WHERE phone = %s", (phone,))
        conn.commit()
        await query.edit_message_text("رزرو شما با موفقیت لغو شد.")
        return MENU

# --- مسیر رزرو ---
async def name_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['name'] = update.message.text
    await update.message.reply_text("شماره تماس خود را وارد کنید:")
    return PHONE

async def phone_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['phone'] = update.message.text
    await update.message.reply_text("سن شما؟")
    return AGE

async def age_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['age'] = update.message.text
    await update.message.reply_text("موضوع جلسه:")
    return ISSUE

async def issue_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['issue'] = update.message.text
    today = jdatetime.date.today()
    dates = []
    for i in range(14):
        day = today + jdatetime.timedelta(days=i)
        if day.weekday() < 5:  # شنبه تا چهارشنبه
            persian_day_list = ["شنبه","یکشنبه","دوشنبه","سه‌شنبه","چهارشنبه","پنج‌شنبه","جمعه"]
            persian_day = persian_day_list[day.weekday()]
            dates.append((day.strftime("%Y/%m/%d"), f"{persian_day} {day.strftime('%Y/%m/%d')}"))
    keyboard = [[InlineKeyboardButton(text, callback_data=f"date_{date}")] for date, text in dates]
    await update.message.reply_text("روز مورد نظر را انتخاب کنید:", reply_markup=InlineKeyboardMarkup(keyboard))
    return DATE

async def date_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    selected_date = query.data.split("_")[1]
    context.user_data['date'] = selected_date
    jalali = jdatetime.datetime.strptime(selected_date, "%Y/%m/%d").date()
    persian_day_list = ["شنبه","یکشنبه","دوشنبه","سه‌شنبه","چهارشنبه","پنج‌شنبه","جمعه"]
    weekday_persian = persian_day_list[jalali.weekday()]
    available_times = PSYCH_SCHEDULE.get(weekday_persian, [])
    c.execute("SELECT time FROM appointments WHERE date = %s AND psych = %s", (selected_date, PSYCH))
    booked = [row[0] for row in c.fetchall()]
    free_times = [t for t in available_times if t not in booked]
    if not free_times:
        await query.edit_message_text("متاسفانه این روز ظرفیت تکمیل است.")
        return MENU
    keyboard = [[InlineKeyboardButton(t, callback_data=f"time_{t}")] for t in free_times]
    await query.edit_message_text("ساعت مورد نظر را انتخاب کنید:", reply_markup=InlineKeyboardMarkup(keyboard))
    return TIME

async def time_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    selected_time = query.data.split("_")[1]
    context.user_data['time'] = selected_time
    user = context.user_data
    link = "https://meet.google.com/new"
    c.execute("""INSERT INTO appointments (name, phone, age, issue, psych, date, time, link, paid)
                 VALUES (%s,%s,%s,%s,%s,%s,%s,%s,0)""",
              (user['name'], user['phone'], user['age'], user['issue'], PSYCH, user['date'], selected_time, link))
    conn.commit()
    await query.edit_message_text(
        f"رزرو شما ثبت شد ✅\n\nروانشناس: {PSYCH}\nزمان: {user['date']} - {selected_time}\nلینک جلسه: {link}"
    )
    await context.bot.send_message(
        ADMIN_CHAT_ID,
        f"رزرو جدید ثبت شد:\nنام: {user['name']}\nشماره: {user['phone']}\nسن: {user['age']}\nموضوع: {user['issue']}\nروانشناس: {PSYCH}\nتاریخ: {user['date']}\nساعت: {selected_time}\nلینک جلسه: {link}"
    )
    return MENU

# --- ویرایش اطلاعات ---
async def name_edit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    new_name = update.message.text
    context.user_data['name'] = new_name
    await update.message.reply_text(f"نام شما با موفقیت به {new_name} تغییر یافت.")
    return MENU

async def phone_edit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    new_phone = update.message.text
    context.user_data['phone'] = new_phone
    await update.message.reply_text(f"شماره شما با موفقیت به {new_phone} تغییر یافت.")
    return MENU

# --- لغو ---
async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("عملیات لغو شد.")
    return MENU

# --- Main ---
def main():
    app = Application.builder().token(TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('start', main_menu)],
        states={
            MENU: [CallbackQueryHandler(menu_choice)],
            NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, name_received)],
            PHONE: [MessageHandler(filters.TEXT & ~filters.COMMAND, phone_received)],
            AGE: [MessageHandler(filters.TEXT & ~filters.COMMAND, age_received)],
            ISSUE: [MessageHandler(filters.TEXT & ~filters.COMMAND, issue_received)],
            DATE: [CallbackQueryHandler(date_chosen)],
            TIME: [CallbackQueryHandler(time_chosen)],
            NAME_EDIT: [MessageHandler(filters.TEXT & ~filters.COMMAND, name_edit)],
            PHONE_EDIT: [MessageHandler(filters.TEXT & ~filters.COMMAND, phone_edit)],
        },
        fallbacks=[CommandHandler('cancel', cancel)]
    )

    app.add_handler(conv_handler)
    app.run_polling()

if __name__ == "__main__":
    main()
