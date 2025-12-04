from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ConversationHandler, MessageHandler, filters, ContextTypes
import jdatetime
import sqlite3
import os

NAME, PHONE, AGE, ISSUE, PSYCH, DATE, TIME = range(7)
TOKEN = os.getenv('TOKEN')

conn = sqlite3.connect('appointments.db', check_same_thread=False)
c = conn.cursor()
c.execute('''CREATE TABLE IF NOT EXISTS appointments
             (id INTEGER PRIMARY KEY, name TEXT, phone TEXT, age TEXT, issue TEXT, psych TEXT, date TEXT, time TEXT, code TEXT)''')
conn.commit()

PSYCHS = {"دکتر محمدی": {
    "شنبه": ["10:00","11:00","14:00","15:00","16:00","17:00","18:00"],
    "یکشنبه": ["10:00","11:00","14:00","15:00","16:00","17:00","18:00"],
    "دوشنبه": ["10:00","11:00","14:00","15:00","16:00","17:00"],
    "سه‌شنبه": ["10:00","11:00","14:00","15:00","16:00"],
    "چهارشنبه": ["10:00","11:00","14:00","15:00","16:00","17:00","18:00"]
}}

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [[InlineKeyboardButton("دکتر محمدی", callback_data="psych_دکتر محمدی")]]
    await update.message.reply_text("سلام 🌸\nروانشناس مورد نظر رو انتخاب کنید:", reply_markup=InlineKeyboardMarkup(keyboard))
    return PSYCH

async def psych_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data['psych'] = "دکتر محمدی"
    await query.edit_message_text("اسم و فامیلتون؟")
    return NAME

async def name_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['name'] = update.message.text
    await update.message.reply_text("شماره تماس؟")
    return PHONE

async def phone_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['phone'] = update.message.text
    await update.message.reply_text("سن؟")
    return AGE

async def age_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['age'] = update.message.text
    await update.message.reply_text("موضوع جلسه؟")
    return ISSUE

async def issue_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['issue'] = update.message.text
    today = jdatetime.date.today()
    dates = []
    for i in range(15):
        day = today + jdatetime.timedelta(days=i)
        if day.weekday() < 5:
            w = ["شنبه","یکشنبه","دوشنبه","سه‌شنبه","چهارشنبه","پنج‌شنبه","جمعه"][day.weekday()]
            dates.append((day.strftime("%Y/%m/%d"), f"{w} {day.strftime('%Y/%m/%d')}"))
    kb = [[InlineKeyboardButton(t, callback_data=f"date_{d}"))] for d, t in dates]
    await update.message.reply_text("روز مورد نظر رو انتخاب کنید:", reply_markup=InlineKeyboardMarkup(kb))
    return DATE

async def date_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    date = query.data.split("_", 1)[1]
    context.user_data['date'] = date
    jalali = jdatetime.date.fromstring(date)
    wd = ["شنبه","یکشنبه","دوشنبه","سه‌شنبه","چهارشنبه","پنج‌شنبه","جمعه"][jalali.weekday()]
    times = PSYCHS["دکتر محمدی"].get(wd, [])
    c.execute("SELECT time FROM appointments WHERE date=?", (date,))
    booked = [r[0] for r in c.fetchall()]
    free = [t for t in times if t not in booked]
    if not free:
        await query.edit_message_text("این روز پره! دوباره /start بزن")
        return ConversationHandler.END
    kb = [[InlineKeyboardButton(t, callback_data=f"time_{t}"))] for t in free]
    await query.edit_message_text(f"ساعت‌های آزاد {wd} {date}:", reply_markup=InlineKeyboardMarkup(kb))
    return TIME

async def time_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    time = query.data.split("_", 1)[1]
    user = context.user_data
    code = str(abs(hash(user["name"] + time + user["date"])))[:6]
    c.execute("INSERT INTO appointments (name,phone,age,issue,psych,date,time,code) VALUES (?,?,?,?,?,?,?,?)",
              (user["name"], user["phone"], user["age"], user["issue"], "دکتر محمدی", user["date"], time, code))
    conn.commit()
    await query.edit_message_text(
        f"نوبت ثبت شد ✅\n\nدکتر محمدی\n{user['date']} ساعت {time}\nلینک: https://meet.google.com/new\n\nکد لغو: `{code}`\n(این کد رو برام بفرستید برای لغو)",
        parse_mode="Markdown"
    )
    return ConversationHandler.END

def main():
    app = Application.builder().token(TOKEN).build()
    app.add_handler(ConversationHandler(
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
    ))
    app.run_polling()

if __name__ == "__main__":
    main()
