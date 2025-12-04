from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ConversationHandler, MessageHandler, filters, ContextTypes
import jdatetime
import psycopg2
import os
from urllib.parse import urlparse

# وضعیت‌های مکالمه
NAME, PHONE, AGE, ISSUE, PSYCH, DATE, TIME = range(7)

# توکن بات
TOKEN = os.getenv('TOKEN')
ADMIN_CHAT_ID = 7548579249

# --- اتصال به PostgreSQL با DATABASE_URL ---
DATABASE_URL = os.getenv("DATABASE_URL") or "postgresql://postgres:dSyLEmnDgGChdXJzygbTMGLNhFYcshtX@interchange.proxy.rlwy.net:52387/railway"
url = urlparse(DATABASE_URL)

conn = psycopg2.connect(
    dbname=url.path[1:],   # اسم دیتابیس
    user=url.username,     # یوزر
    password=url.password, # پسورد
    host=url.hostname,     # هاست
    port=url.port          # پورت
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

# ساعات کاری روانشناسان
PSYCHS = {
    "دکتر رضائی": {
        "شنبه": ["10:00", "11:00", "14:00", "15:00", "16:00", "17:00", "18:00"],
        "یکشنبه": ["10:00", "11:00", "14:00", "15:00", "16:00", "17:00", "18:00"],
        "دوشنبه": ["10:00", "11:00", "14:00", "15:00", "16:00", "17:00"],
        "سه‌شنبه": ["10:00", "11:00", "14:00", "15:00", "16:00"],
        "چهارشنبه": ["10:00", "11:00", "14:00", "15:00", "16:00", "17:00", "18:00"]
    }
}

# --- START ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [[InlineKeyboardButton(psych, callback_data=f"psych_{psych}")] for psych in PSYCHS.keys()]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        "سلام، خوش آمدید.\nلطفاً روانشناس مورد نظر را انتخاب کنید:",
        reply_markup=reply_markup
    )
    return PSYCH

async def psych_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    psych = query.data.split("_")[1]
    context.user_data['psych'] = psych
    await query.edit_message_text(
        f"روانشناس انتخاب شده: {psych}\n\nلطفاً نام و نام خانوادگی خود را وارد کنید:"
    )
    return NAME

async def name_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['name'] = update.message.text
    await update.message.reply_text("شماره تماس خود را ارسال کنید:")
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
        if day.weekday() < 5:
            persian_day_list = ["شنبه","یکشنبه","دوشنبه","سه‌شنبه","چهارشنبه","پنج‌شنبه","جمعه"]
            persian_day = persian_day_list[day.weekday()]
            dates.append((day.strftime("%Y/%m/%d"), f"{persian_day} {day.strftime('%Y/%m/%d')}"))
    keyboard = [[InlineKeyboardButton(text, callback_data=f"date_{date}")] for date, text in dates]
    await update.message.reply_text(
        "روز مورد نظر را انتخاب کنید:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return DATE

async def date_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    selected_date = query.data.split("_")[1]
    context.user_data['date'] = selected_date
    jalali = jdatetime.datetime.strptime(selected_date, "%Y/%m/%d").date()
    persian_day_list = ["شنبه","یکشنبه","دوشنبه","سه‌شنبه","چهارشنبه","پنج‌شنبه","جمعه"]
    weekday_persian = persian_day_list[jalali.weekday()]
    psych = context.user_data['psych']
    available_times = PSYCHS[psych].get(weekday_persian, [])
    c.execute("SELECT time FROM appointments WHERE date = %s AND psych = %s", (selected_date, psych))
    booked = [row[0] for row in c.fetchall()]
    free_times = [t for t in available_times if t not in booked]
    if not free_times:
        await query.edit_message_text("متاسفانه این روز ظرفیت تکمیل است.")
        return ConversationHandler.END
    keyboard = [[InlineKeyboardButton(t, callback_data=f"time_{t}")] for t in free_times]
    await query.edit_message_text(
        "ساعت مورد نظر را انتخاب کنید:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
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
              (user['name'], user['phone'], user['age'], user['issue'],
               user['psych'], user['date'], selected_time, link))
    conn.commit()
    await query.edit_message_text(
        f"رزرو شما با موفقیت ثبت شد.\n\nروانشناس: {user['psych']}\nزمان: {user['date']} - {selected_time}\nلینک جلسه: {link}"
    )
    await context.bot.send_message(
        ADMIN_CHAT_ID,
        f"رزرو جدید ثبت شد:\n\nنام: {user['name']}\nشماره: {user['phone']}\nسن: {user['age']}\nموضوع: {user['issue']}\nروانشناس: {user['psych']}\nتاریخ: {user['date']}\nساعت: {selected_time}\nلینک جلسه: {link}"
    )
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("عملیات لغو شد.")
    return ConversationHandler.END

# --- Main ---
def main():
    app = Application.builder().token(TOKEN).build()
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('start', start)],
        states={
            PSYCH: [CallbackQueryHandler(psych_chosen)],
            NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, name_received)],
            PHONE: [MessageHandler(filters.TEXT & ~filters.COMMAND, phone_received)],
            AGE: [MessageHandler(filters.TEXT & ~filters.COMMAND, age_received)],
            ISSUE: [MessageHandler(filters.TEXT & ~filters.COMMAND, issue_received)],
            DATE: [CallbackQueryHandler(date_chosen)],
            TIME: [CallbackQueryHandler(time_chosen)],
        },
        fallbacks=[CommandHandler('cancel', cancel)]
    )
    app.add_handler(conv_handler)
    app.run_polling()

if __name__ == "__main__":
    main()
