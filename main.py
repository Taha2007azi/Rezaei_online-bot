from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    ConversationHandler, MessageHandler, filters, ContextTypes
)
import jdatetime
import sqlite3
import os

# وضعیت‌ها
(NAME, PHONE, AGE, ISSUE, PSYCH, DATE, TIME) = range(7)

TOKEN = os.getenv('TOKEN')
ADMIN_USERNAME = "@Taha2007azi"

# دیتابیس
conn = sqlite3.connect('appointments.db', check_same_thread=False)
c = conn.cursor()
c.execute('''CREATE TABLE IF NOT EXISTS appointments
             (id INTEGER PRIMARY KEY, name TEXT, phone TEXT, age INTEGER, issue TEXT,
              psych TEXT, date TEXT, time TEXT, link TEXT, paid INTEGER, code TEXT)''')
conn.commit()

# روانشناس‌ها
PSYCHS = {"دکتر محمدی": {
    "شنبه": ["10:00", "11:00", "14:00", "15:00", "16:00", "17:00", "18:00"],
    "یکشنبه": ["10:00", "11:00", "14:00", "15:00", "16:00", "17:00", "18:00"],
    "دوشنبه": ["10:00", "11:00", "14:00", "15:00", "16:00", "17:00"],
    "سه‌شنبه": ["10:00", "11:00", "14:00", "15:00", "16:00"],
    "چهارشنبه": ["10:00", "11:00", "14:00", "15:00", "16:00", "17:00", "18:00"]
}}

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [[InlineKeyboardButton(p, callback_data=f"psych_{p}")] for p in PSYCHS]
    await update.message.reply_text("سلام! به بات رزرو نوبت خوش آمدید 🌸\nروانشناس رو انتخاب کنید:", reply_markup=InlineKeyboardMarkup(keyboard))
    return PSYCH

async def psych_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    psych = query.data.replace("psych_", "")
    context.user_data["psych"] = psych
    await query.edit_message_text(f"روانشناس: {psych}\n\nاسم و فامیلتون؟")
    return NAME

async def name_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["name"] = update.message.text
    await update.message.reply_text("شماره تماس؟")
    return PHONE

async def phone_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["phone"] = update.message.text
    await update.message.reply_text("سن؟")
    return AGE

async def age_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["age"] = update.message.text
    await update.message.reply_text("موضوع جلسه؟ (مثلاً اضطراب، رابطه و...)")
    return ISSUE

async def issue_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["issue"] = update.message.text
    today = jdatetime.date.today()
    dates = []
    for i in range(14):
        day = today + jdatetime.timedelta(days=i)
        if day.weekday() < 5:
            persian_day = ["شنبه", "یکشنبه", "دوشنبه", "سه‌شنبه", "چهارشنبه", "پنج‌شنبه", "جمعه"][day.weekday()]
            dates.append((day.strftime("%Y/%m/%d"), f"{persian_day} {day.strftime('%Y/%m/%d')}"))
    keyboard = [[InlineKeyboardButton(text, callback_data=f"date_{d}")] for d, text in dates]
    await update.message.reply_text("روز رو انتخاب کنید:", reply_markup=InlineKeyboardMarkup(keyboard))
    return DATE

async def date_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    date = query.data.replace("date_", "")
    context.user_data["date"] = date
    jalali = jdatetime.date.fromstring(date)
    weekday = ["شنبه", "یکشنبه", "دوشنبه", "سه‌شنبه", "چهارشنبه", "پنج‌شنبه", "جمعه"][jalali.weekday()]
    psych = context.user_data["psych"]
    times = PSYCHS[psych].get(weekday, [])
    c.execute("SELECT time FROM appointments WHERE date=? AND psych=?", (date, psych))
    booked = [row[0] for row in c.fetchall()]
    free = [t for t in times if t not in booked]
    if not free:
        await query.edit_message_text("این روز پره! دوباره /start بزنید.")
        return ConversationHandler.END
    keyboard = [[InlineKeyboardButton(t, callback_data=f"time_{t}")] for t in free]
    await query.edit_message_text(f"ساعت‌های آزاد {weekday} {date}:\nانتخاب کنید:", reply_markup=InlineKeyboardMarkup(keyboard))
    return TIME

async def time_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    time = query.data.replace("time_", "")
    context.user_data["time"] = time
    user = context.user_data
    code = str(abs(hash(user["name"] + time + user["date"])))[:6]
    c.execute("INSERT INTO appointments (name,phone,age,issue,psych,date,time,link,paid,code) VALUES (?,?,?,?,?,?,?,?,0,?)",
              (user["name"], user["phone"], user["age"], user["issue"], user["psych"], user["date"], time, "https://meet.google.com/new", code))
    conn.commit()
    await query.edit_message_text(
        f"نوبت ثبت شد! ✅\n\nروانشناس: {user['psych']}\nروز: {user['date']} ساعت {time}\nلینک: https://meet.google.com/new\n\nکد لغو: `{code}`\n(فقط این کد رو برام بفرستید برای لغو)",
        parse_mode="Markdown"
    )
    # نوتیف به تو
    try:
        await context.bot.send_message(ADMIN_USERNAME,
            f"نوبت جدید!\nنام: {user['name']}\nتلفن: {user['phone']}\nسن: {user['age']}\nموضوع: {user['issue']}\nروانشناس: {user['psych']}\n{user['date']} ساعت {time}\nکد لغو: {code}")
    except: pass
    return ConversationHandler.END

async def cancel_appointment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    code = update.message.text.strip()
    c.execute("SELECT * FROM appointments WHERE code=?", (code,))
    row = c.fetchone()
    if row and row[9] == 0:
        c.execute("DELETE FROM appointments WHERE code=?", (code,))
        conn.commit()
        await update.message.reply_text(f"نوبت با کد {code} لغو شد ✅")
        await context.bot.send_message(ADMIN_USERNAME, f"لغو شد!\nنام: {row[1]}\n{row[6]} ساعت {row[7]}")
    else:
        await update.message.reply_text("کد اشتباه یا قبلاً لغو شده.")
    return ConversationHandler.END

def main():
    app = Application.builder().token(TOKEN).build()
    app.add_handler(ConversationHandler(
        entry_points=[CommandHandler("start", start),
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
        fallbacks=[CommandHandler("cancel", lambda u,c: ConversationHandler.END)]
    ))
    app.run_polling()

if __name__ == "__main__":
    main()
