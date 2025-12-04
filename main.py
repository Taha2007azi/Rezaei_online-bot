from telegram import Update, ReplyKeyboardMarkup, ForceReply
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ConversationHandler, MessageHandler, filters, ContextTypes
import jdatetime
import sqlite3
import os

# وضعیت‌های مکالمه
START_MENU, PSYCH, NAME, PHONE, AGE, ISSUE, DATE, TIME = range(8)

TOKEN = os.getenv('TOKEN')
ADMIN_CHAT_ID = 7548579249

# اتصال به دیتابیس
conn = sqlite3.connect('appointments.db', check_same_thread=False)
c = conn.cursor()
c.execute('''CREATE TABLE IF NOT EXISTS appointments
             (id INTEGER PRIMARY KEY, name TEXT, phone TEXT, age INTEGER,
              issue TEXT, psych TEXT, date TEXT, time TEXT, link TEXT, paid INTEGER)''')
conn.commit()

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
    keyboard = [["شروع رزرو", "چک کردن رزرو"], ["لغو"]]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    await update.message.reply_text("سلام! گزینه مورد نظر را انتخاب کنید:", reply_markup=reply_markup)
    return START_MENU

async def start_menu_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    if text == "شروع رزرو":
        keyboard = [[psych] for psych in PSYCHS.keys()]
        reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)
        await update.message.reply_text("لطفاً روانشناس مورد نظر را انتخاب کنید:", reply_markup=reply_markup)
        return PSYCH
    elif text == "چک کردن رزرو":
        c.execute("SELECT name, phone, date, time FROM appointments")
        rows = c.fetchall()
        if rows:
            msg = "رزروهای فعلی:\n" + "\n".join([f"{name} - {phone} - {date} {time}" for name, phone, date, time in rows])
        else:
            msg = "رزروی ثبت نشده است."
        await update.message.reply_text(msg)
        return START_MENU
    elif text == "لغو":
        await update.message.reply_text("عملیات لغو شد.")
        return ConversationHandler.END
    else:
        await update.message.reply_text("لطفاً یکی از گزینه‌ها را انتخاب کنید.")
        return START_MENU

# --- رزرو ---
async def psych_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    psych = update.message.text
    context.user_data['psych'] = psych
    await update.message.reply_text("لطفاً نام و نام خانوادگی خود را وارد کنید:", reply_markup=ForceReply(selective=True))
    return NAME

async def name_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['name'] = update.message.text
    await update.message.reply_text("شماره تماس خود را وارد کنید:", reply_markup=ForceReply(selective=True))
    return PHONE

async def phone_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['phone'] = update.message.text
    await update.message.reply_text("سن شما؟", reply_markup=ForceReply(selective=True))
    return AGE

async def age_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['age'] = update.message.text
    await update.message.reply_text("موضوع جلسه:", reply_markup=ForceReply(selective=True))
    return ISSUE

async def issue_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['issue'] = update.message.text

    today = jdatetime.date.today()
    dates = []
    for i in range(14):
        day = today + jdatetime.timedelta(days=i)
        if day.weekday() < 5:
            persian_day_list = ["شنبه", "یکشنبه", "دوشنبه", "سه‌شنبه","چهارشنبه", "پنج‌شنبه", "جمعه"]
            persian_day = persian_day_list[day.weekday()]
            dates.append((day.strftime("%Y/%m/%d"), f"{persian_day} {day.strftime('%Y/%m/%d')}"))

    keyboard = [[date, ] for date, text in dates]
    reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)
    await update.message.reply_text("روز مورد نظر را انتخاب کنید:", reply_markup=reply_markup)
    return DATE

async def date_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    selected_date = update.message.text
    context.user_data['date'] = selected_date

    jalali = jdatetime.datetime.strptime(selected_date, "%Y/%m/%d").date()
    persian_day_list = ["شنبه", "یکشنبه", "دوشنبه", "سه‌شنبه","چهارشنبه", "پنج‌شنبه", "جمعه"]
    weekday_persian = persian_day_list[jalali.weekday()]

    psych = context.user_data['psych']
    available_times = PSYCHS[psych].get(weekday_persian, [])
    c.execute("SELECT time FROM appointments WHERE date = ? AND psych = ?", (selected_date, psych))
    booked = [row[0] for row in c.fetchall()]
    free_times = [t for t in available_times if t not in booked]

    if not free_times:
        await update.message.reply_text("متاسفانه این روز ظرفیت تکمیل است.")
        return ConversationHandler.END

    keyboard = [[t] for t in free_times]
    reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)
    await update.message.reply_text("ساعت مورد نظر را انتخاب کنید:", reply_markup=reply_markup)
    return TIME

async def time_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    selected_time = update.message.text
    context.user_data['time'] = selected_time
    user = context.user_data
    link = "https://meet.google.com/new"

    c.execute("""INSERT INTO appointments (name, phone, age, issue, psych, date, time, link, paid)
                 VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0)""",
              (user['name'], user['phone'], user['age'], user['issue'], user['psych'], user['date'], selected_time, link))
    conn.commit()

    await update.message.reply_text(
        f"رزرو شما با موفقیت ثبت شد.\n\n"
        f"روانشناس: {user['psych']}\n"
        f"زمان: {user['date']} - {selected_time}\n"
        f"لینک جلسه: {link}"
    )

    await context.bot.send_message(
        ADMIN_CHAT_ID,
        f"رزرو جدید ثبت شد:\n\n"
        f"نام: {user['name']}\n"
        f"شماره: {user['phone']}\n"
        f"سن: {user['age']}\n"
        f"موضوع: {user['issue']}\n"
        f"روانشناس: {user['psych']}\n"
        f"تاریخ: {user['date']}\n"
        f"ساعت: {selected_time}\n"
        f"لینک جلسه: {link}"
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
            START_MENU: [MessageHandler(filters.TEXT & ~filters.COMMAND, start_menu_choice)],
            PSYCH: [MessageHandler(filters.TEXT & ~filters.COMMAND, psych_chosen)],
            NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, name_received)],
            PHONE: [MessageHandler(filters.TEXT & ~filters.COMMAND, phone_received)],
            AGE: [MessageHandler(filters.TEXT & ~filters.COMMAND, age_received)],
            ISSUE: [MessageHandler(filters.TEXT & ~filters.COMMAND, issue_received)],
            DATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, date_chosen)],
            TIME: [MessageHandler(filters.TEXT & ~filters.COMMAND, time_chosen)],
        },
        fallbacks=[CommandHandler('cancel', cancel)]
    )

    app.add_handler(conv_handler)
    app.run_polling()

if __name__ == "__main__":
    main()
