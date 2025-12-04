from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ConversationHandler, MessageHandler, filters, ContextTypes
import jdatetime
import sqlite3
import os

# وضعیت‌ها
(NAME, PHONE, AGE, ISSUE, PSYCH, DATE, TIME) = range(7)

TOKEN = os.getenv('TOKEN')

# دیتابیس + کد لغو
conn = sqlite3.connect('appointments.db', check_same_thread=False)
c = conn.cursor()
c.execute('''CREATE TABLE IF NOT EXISTS appointments
             (id INTEGER PRIMARY KEY, name TEXT, phone TEXT, age TEXT, issue TEXT, 
              psych TEXT, date TEXT, time TEXT, link TEXT, paid INTEGER, cancel_code TEXT)''')
conn.commit()

# روانشناس و ساعت‌ها
PSYCHS = {"دکتر محمدی": {
    "شنبه": ["10:00","11:00","14:00","15:00","16:00","17:00","18:00"],
    "یکشنبه": ["10:00","11:00","14:00","15:00","16:00","17:00","18:00"],
    "دوشنبه": ["10:00","11:00","14:00","15:00","16:00","17:00"],
    "سه‌شنبه": ["10:00","11:00","14:00","15:00","16:00"],
    "چهارشنبه": ["10:00","11:00","14:00","15:00","16:00","17:00","18:00"]
}}

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    kb = [[InlineKeyboardButton("دکتر محمدی", callback_data="psych_دکتر محمدی")]]
    await update.message.reply_text("سلام! به بات رزرو نوبت مشاوره خوش آمدید 🌸\nروانشناس رو انتخاب کنید:", reply_markup=InlineKeyboardMarkup(kb))
    return PSYCH

async def psych_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data["psych"] = "دکتر محمدی"
    await query.edit_message_text("نام و نام خانوادگی:")
    return NAME

async def name_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["name"] = update.message.text
    await update.message.reply_text("شماره تماس:")
    return PHONE

async def phone_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["phone"] = update.message.text
    await update.message.reply_text("سن:")
    return AGE

async def age_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["age"] = update.message.text
    await update.message.reply_text("موضوع جلسه (مثل اضطراب، افسردگی، رابطه...):")
    return ISSUE

async def issue_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["issue"] = update.message.text
    today = jdatetime.date.today()
    dates = []
    for i in range(14):
        day = today + jdatetime.timedelta(days=i)
        if day.weekday() < 5:  # فقط شنبه تا چهارشنبه
            wd = ["شنبه","یکشنبه","دوشنبه","سه‌شنبه","چهارشنبه","پنج‌شنبه","جمعه"][day.weekday()]
            dates.append((day.strftime("%Y/%m/%d"), f"{wd} {day.strftime('%Y/%m/%d')}"))
    kb = [[InlineKeyboardButton(text, callback_data=f"date_{date}")] for date, text in dates]
    await update.message.reply_text("روز مورد نظر رو انتخاب کنید:", reply_markup=InlineKeyboardMarkup(kb))
    return DATE

async def date_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    selected_date = query.data.split("_", 1)[1]
    context.user_data["date"] = selected_date
    
    jalali_date = jdatetime.date.fromstring(selected_date)
    weekday = ["شنبه","یکشنبه","دوشنبه","سه‌شنبه","چهارشنبه","پنج‌شنبه","جمعه"][jalali_date.weekday()]
    
    times = PSYCHS["دکتر محمدی"].get(weekday, [])
    c.execute("SELECT time FROM appointments WHERE date = ? AND psych = ?", (selected_date, "دکتر محمدی"))
    booked = [row[0] for row in c.fetchall()]
    free_times = [t for t in times if t not in booked]
    
    if not free_times:
        await query.edit_message_text("این روز دیگه وقتی خالی نداره 😔\nدوباره /start بزنید.")
        return ConversationHandler.END
    
    kb = [[InlineKeyboardButton(t, callback_data=f"time_{t}")] for t in free_times]
    await query.edit_message_text(f"ساعت‌های آزاد {weekday} {selected_date}:\nانتخاب کنید:", reply_markup=InlineKeyboardMarkup(kb))
    return TIME

async def time_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    selected_time = query.data.split("_", 1)[1]
    user = context.user_data
    
    # کد ۶ رقمی منحصر به فرد
    cancel_code = str(abs(hash(f"{user['name']}{user['phone']}{user['date']}{selected_time}")))[:6]
    
    c.execute("""INSERT INTO appointments 
                 (name, phone, age, issue, psych, date, time, link, paid, cancel_code) 
                 VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, ?)""",
              (user['name'], user['phone'], user['age'], user['issue'], "دکتر محمدی", 
               user['date'], selected_time, "https://meet.google.com/new", cancel_code))
    conn.commit()
    
    await query.edit_message_text(
        f"نوبت با موفقیت ثبت شد! ✅\n\n"
        f"روانشناس: دکتر محمدی\n"
        f"روز: {user['date']} ساعت {selected_time}\n"
        f"لینک جلسه: https://meet.google.com/new\n\n"
        f"کد لغو نوبت شما: `{cancel_code}`\n"
        f"برای لغو، فقط این کد رو برام بفرستید.",
        parse_mode="Markdown"
    )
    return ConversationHandler.END

# لغو نوبت با کد
async def cancel_appointment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    code = update.message.text.strip()
    c.execute("SELECT * FROM appointments WHERE cancel_code = ? AND paid = 0", (code,))
    apt = c.fetchone()
    if apt:
        c.execute("DELETE FROM appointments WHERE cancel_code = ?", (code,))
        conn.commit()
        await update.message.reply_text(f"نوبت شما با موفقیت لغو شد ✅\nروز: {apt[6]} ساعت {apt[7]}")
    else:
        await update.message.reply_text("کد اشتباه است یا نوبت قبلاً لغو شده.")
    return ConversationHandler.END

def main():
    app = Application.builder().token(TOKEN).build()
    
    # مکالمه اصلی
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            PSYCH: [CallbackQueryHandler(psych_chosen)],
            NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, name_received)],
            PHONE: [MessageHandler(filters.TEXT & ~filters.COMMAND, phone_received)],
            AGE: [MessageHandler(filters.TEXT & ~filters.COMMAND, age_received)],
            ISSUE: [MessageHandler(filters.TEXT & ~filters.COMMAND, issue_received)],
            DATE: [CallbackQueryHandler(date_chosen)],
            TIME: [CallbackQueryHandler(time_chosen)],
        },
        fallbacks=[]
    )
    
    app.add_handler(conv_handler)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, cancel_appointment))
    app.run_polling()

if __name__ == "__main__":
    main()
