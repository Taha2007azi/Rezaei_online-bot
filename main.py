from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ConversationHandler, MessageHandler, filters, ContextTypes
import jdatetime
import sqlite3
import os

(NAME, PHONE, AGE, ISSUE, PSYCH, DATE, TIME) = range(7)
TOKEN = os.getenv('TOKEN')
ADMIN = "@Taha2007azi"

conn = sqlite3.connect('appointments.db', check_same_thread=False)
c = conn.cursor()
c.execute('''CREATE TABLE IF NOT EXISTS appointments
             (name TEXT, phone TEXT, age TEXT, issue TEXT, psych TEXT, date TEXT, time TEXT, code TEXT)''')
conn.commit()

PSYCHS = {"دکتر محمدی": {
    "شنبه": ["10:00","11:00","14:00","15:00","16:00","17:00","18:00"],
    "یکشنبه": ["10:00","11:00","14:00","15:00","16:00","17:00","18:00"],
    "دوشنبه": ["10:00","11:00","14:00","15:00","16:00","17:00"],
    "سه‌شنبه": ["10:00","11:00","14:00","15:00","16:00"],
    "چهارشنبه": ["10:00","11:00","14:00","15:00","16:00","17:00","18:00"]
}}

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    kb = [[InlineKeyboardButton(p, callback_data=f"psych:{p}")] for p in PSYCHS]
    await update.message.reply_text("سلام 🌸\nروانشناس رو انتخاب کن:", reply_markup=InlineKeyboardMarkup(kb))
    return PSYCH

async def psych_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    psych = q.data.split(":")[1]
    context.user_data["psych"] = psych
    await q.edit_message_text(f"روانشناس: {psych}\n\nاسم و فامیل؟")
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
    await update.message.reply_text("موضوع جلسه؟")
    return ISSUE

async def issue_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["issue"] = update.message.text
    today = jdatetime.date.today()
    dates = []
    for i in range(15):
        d = today + jdatetime.timedelta(days=i)
        if d.weekday() < 5:
            wd = ["شنبه","یکشنبه","دوشنبه","سه‌شنبه","چهارشنبه","پنج‌شنبه","جمعه"][d.weekday()]
            dates.append((d.strftime("%Y/%m/%d"), f"{wd} {d.strftime('%Y/%m/%d')}"))
    kb = [[InlineKeyboardButton(t, callback_data=f"date:{d}")] for d, t in dates]
    await update.message.reply_text("روز رو انتخاب کن:", reply_markup=InlineKeyboardMarkup(kb))
    return DATE

async def date_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    date = q.data.split(":")[1]
    context.user_data["date"] = date
    jalali = jdatetime.date.fromstring(date)
    wd = ["شنبه","یکشنبه","دوشنبه","سه‌شنبه","چهارشنبه","پنج‌شنبه","جمعه"][jalali.weekday()]
    times = PSYCHS[context.user_data["psych"]].get(wd, [])
    c.execute("SELECT time FROM appointments WHERE date=? AND psych=?", (date, context.user_data["psych"]))
    booked = [r[0] for r in c.fetchall()]
    free = [t for t in times if t not in booked]
    if not free:
        await q.edit_message_text("این روز پره!\n/start بزن دوباره")
        return ConversationHandler.END
    kb = [[InlineKeyboardButton(t, callback_data=f"time:{t}")] for t in free]
    await q.edit_message_text(f"ساعت آزاد {wd} {date}:", reply_markup=InlineKeyboardMarkup(kb))
    return TIME

async def time_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    time = q.data.split(":")[1]
    u = context.user_data
    code = str(abs(hash(u["name"]+time+u["date"])))[:6]
    c.execute("INSERT INTO appointments VALUES (?,?,?,?,?,?,?,?)",
              (u["name"], u["phone"], u["age"], u["issue"], u["psych"], u["date"], time, code))
    conn.commit()
    await q.edit_message_text(
        f"نوبت ثبت شد ✅\n\n{u['psych']}\n{u['date']} ساعت {time}\nلینک: https://meet.google.com/new\n\nکد لغو: `{code}`",
        parse_mode="Markdown"
    )
    try:
        await context.bot.send_message(ADMIN, f"نوبت جدید!\n{u['name']} - {u['phone']}\n{u['psych']} | {u['date']} | {time}\nکد: {code}")
    except: pass
    return ConversationHandler.END

async def cancel_appointment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    code = update.message.text.strip()
    c.execute("SELECT * FROM appointments WHERE code=?", (code,))
    r = c.fetchone()
    if r:
        c.execute("DELETE FROM appointments WHERE code=?", (code,))
        conn.commit()
        await update.message.reply_text("نوبت لغو شد ✅")
        await context.bot.send_message(ADMIN, f"لغو شد:\n{r[0]} | {r[5]} | {r[6]}")
    else:
        await update.message.reply_text("کد پیدا نشد.")
    return ConversationHandler.END

def main():
    app = Application.builder().token(TOKEN).build()
    app.add_handler(ConversationHandler(
        entry_points=[CommandHandler("start", start), MessageHandler(filters.TEXT & ~filters.COMMAND, cancel_appointment)],
        states={
            PSYCH: [CallbackQueryHandler(psych_chosen, pattern=r"^psych:.+")],
            NAME:   [MessageHandler(filters.TEXT & ~filters.COMMAND, name_received)],
            PHONE:  [MessageHandler(filters.TEXT & ~filters.COMMAND, phone_received)],
            AGE:    [MessageHandler(filters.TEXT & ~filters.COMMAND, age_received)],
            ISSUE:  [MessageHandler(filters.TEXT & ~filters.COMMAND, issue_received)],
            DATE:   [CallbackQueryHandler(date_chosen, pattern=r"^date:.+")],
            TIME:   [CallbackQueryHandler(time_chosen, pattern=r"^time:.+")],
        },
        fallbacks=[]
    ))
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
