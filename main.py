from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    ConversationHandler, MessageHandler, filters, ContextTypes
)
import jdatetime
import sqlite3
import os

# وضعیت‌ها
NAME, PHONE, AGE, ISSUE, PSYCH, DATE, TIME = range(7)

TOKEN = os.getenv('TOKEN')
ADMIN_USERNAME = "@Taha2007azi"  # تو

# دیتابیس
conn = sqlite3.connect('appointments.db', check_same_thread=False)
c = conn.cursor()
c.execute('''CREATE TABLE IF NOT EXISTS appointments
             (id INTEGER PRIMARY KEY, name TEXT, phone TEXT, age INTEGER, issue TEXT,
              psych TEXT, date TEXT, time TEXT, link TEXT, paid INTEGER, code TEXT)''')
conn.commit()

# روانشناس‌ها و ساعت‌ها
PSYCHS = {
    "دکتر محمدی": {
        "شنبه": ["10:00", "11:00", "14:00", "15:00", "16:00", "17:00", "18:00"],
        "یکشنبه": ["10:00", "11:00", "14:00", "15:00", "16:00", "17:00", "18:00"],
        "دوشنبه": ["10:00", "11:00", "14:00", "15:00", "16:00", "17:00"],
        "سه‌شنبه": ["10:00", "11:00", "14:00", "15:00", "16:00"],
        "چهارشنبه": ["10:00", "11:00", "14:00", "15:00", "16:00", "17:00", "18:00"]
    }
}

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [[InlineKeyboardButton(psych, callback_data=f"psych_{psych}")] for psych in PSYCHS.keys()]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        "سلام! به بات رزرو نوبت مشاوره خوش آمدید 🌸\nلطفاً روانشناس مورد نظرتون رو انتخاب کنید:",
        reply_markup=reply_markup
    )
    return PSYCH

async def psych_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    psych = query.data.split("_")[1]
    context.user_data['psych'] = psych
    await query.edit_message_text(f"روانشناس: {psych}\n\nنام و نام خانوادگی‌تون رو بفرستید:")
    return NAME

async def name_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['name'] = update.message.text
    await update.message.reply_text("شماره تماس (جهت یادآوری):")
    return PHONE

async def phone_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['phone'] = update.message.text
    await update.message.reply_text("سن:")
    return AGE

async def age_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['age'] = update.message.text
    await update.message.reply_text("موضوع جلسه (مثلاً اضطراب، رابطه، افسردگی...):")
    return ISSUE

async def issue_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['issue'] = update.message.text
    today = jdatetime.date.today()
    dates = []
    for i in range(14):
        day = today + jdatetime.timedelta(days=i)
        if day.weekday() < 5:  # شنبه تا چهارشنبه
            persian_day = ["شنبه", "یکشنبه", "دوشنبه", "سه‌شنبه", "چهارشنبه", "پنج‌شنبه", "جمعه"][day.weekday()]
            dates.append((day.strftime("%Y/%m/%d"), f"{persian_day} {day.strftime('%Y/%m/%d')}"))
    
    keyboard = [[InlineKeyboardButton(text, callback_data=f"date_{date}")] for date, text in dates]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("روز مورد نظرتون رو انتخاب کنید:", reply_markup=reply_markup)
    return DATE

async def date_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    selected_date = query.data.split("_")[1]
    context.user_data['date'] = selected_date
    
    jalali = jdatetime.date.fromstring(selected_date)
    weekday_persian = ["شنبه", "یکشنبه", "دوشنبه", "سه‌شنبه", "چهارشنبه", "پنج‌شنبه", "جمعه"][jalali.weekday()]
    psych = context.user_data['psych']
    
    available_times = PSYCHS[psych].get(weekday_persian, [])
    c.execute("SELECT time FROM appointments WHERE date = ? AND psych = ?", (selected_date, psych))
    booked = [row[0] for row in c.fetchall()]
    free_times = [t for t in available_times if t not in booked]
    
    if not free_times:
        await query.edit_message_text("متاسفانه این روز دیگه وقتی خالی نیست 😔\nدوباره /start بزنید.")
        return ConversationHandler.END
    
    keyboard = [[InlineKeyboardButton(t, callback_data=f"time_{t}")] for t in free_times]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(f"ساعت‌های آزاد {weekday_persian} {jalali.strftime('%Y/%m/%d')}:\nانتخاب کنید:", reply_markup=reply_markup)
    return TIME

async def time_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    selected_time = query.data.split("_")[1]
    context.user_data['time'] = selected_time
    
    user = context.user_data
    link = "https://meet.google.com/new"
    cancel_code = str(abs(hash(f"{user['name']}{selected_time}{user['date']}")))[:6]

    c.execute("""INSERT INTO appointments 
                 (name, phone, age, issue, psych, date, time, link, paid, code) 
                 VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, ?)""",
              (user['name'], user['phone'], user['age'], user['issue'], user['psych'],
               user['date'], selected_time, link, cancel_code))
    conn.commit()
    
    await query.edit_message_text(
        f"نوبت با موفقیت ثبت شد! ✅\n\n"
        f"روانشناس: {user['psych']}\n"
        f"روز: {user['date']} ساعت {selected_time}\n"
        f"لینک جلسه: {link}\n\n"
        f"کد لغو نوبت شما: `{cancel_code}`\n"
        f"برای لغو، فقط این کد رو برام بفرستید.",
        parse_mode='Markdown'
    )
    
    # نوتیف فوری به تو
    try:
        await context.bot.send_message(
            chat_id=ADMIN_USERNAME,
            text=f"نوبت جدید!\n\n"
                 f"نام: {user['name']}\n"
                 f"تلفن: {user['phone']}\n"
                 f"سن: {user['age']}\n"
                 f"موضوع: {user['issue']}\n"
                 f"روانشناس: {user['psych']}\n"
                 f"روز: {user['date']} ساعت {user['time']}\n"
                 f"کد لغو: {cancel_code}"
        )
    except Exception as e:
        print("خطا در ارسال نوتیف:", e)
    
    return ConversationHandler.END

# لغو نوبت
async def cancel_appointment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    code = update.message.text.strip()
    c.execute("SELECT * FROM appointments WHERE code = ?", (code,))
    apt = c.fetchone()
    
    if apt and apt[9] == 0:
        c.execute("DELETE FROM appointments WHERE code = ?", (code,))
        conn.commit()
        await update.message.reply_text(f"نوبت با کد `{code}` با موفقیت لغو شد ✅", parse_mode='Markdown')
        await context.bot.send_message(
            chat_id=ADMIN_USERNAME,
            text=f"لغو نوبت!\n\nنام: {apt[1]}\nتلفن: {apt[2]}\nروانشناس: {apt[5]}\nروز: {apt[6]} ساعت {apt[7]}"
        )
    else:
        await update.message.reply_text("کد اشتباه است یا نوبت قبلاً لغو شده.")
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("عملیات لغو شد. دوباره /start بزنید.")
    return ConversationHandler.END

def main():
    app = Application.builder().token(TOKEN).build()
    
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('start', start),
                      MessageHandler(filters.TEXT & ~filters.COMMAND, cancel_appointment)],
        states={
            PSYCH: [CallbackQueryHandler(psych_chosen, pattern="^psych_")],
            NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, name_received)],
            PHONE: [MessageHandler(filters.TEXT & ~filters.COMMAND, phone_received)],
            AGE: [MessageHandler(filters.TEXT & ~filters.COMMAND, age_received)],
            ISSUE: [MessageHandler(filters.TEXT & ~filters.COMMAND, issue_received)],
            DATE: [CallbackQueryHandler(date_chosen, pattern="^date_")],
            TIME: [CallbackQueryHandler(time_chosen, pattern="^time_")],
        },
        fallbacks=[CommandHandler('cancel', cancel)]
    )
    
    app.add_handler(conv_handler)
    app.run_polling()

if __name__ == '__main__':
    main()
