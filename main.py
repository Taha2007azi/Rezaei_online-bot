from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ConversationHandler, MessageHandler, filters, ContextTypes
import jdatetime
import psycopg2
import os
from urllib.parse import urlparse

# مراحل مکالمه
NAME, PHONE, AGE, ISSUE, DATE, TIME = range(6)

TOKEN = os.getenv("TOKEN")
ADMIN_CHAT_ID = 7548579249

# اتصال به PostgreSQL با DATABASE_URL
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

# ساخت جدول
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

# ساعات کاری رضائی
AVAILABLE_TIMES = {
    "شنبه": ["10:00", "11:00", "14:00", "15:00", "16:00", "17:00", "18:00"],
    "یکشنبه": ["10:00", "11:00", "14:00", "15:00", "16:00", "17:00", "18:00"],
    "دوشنبه": ["10:00", "11:00", "14:00", "15:00", "16:00", "17:00"],
    "سه‌شنبه": ["10:00", "11:00", "14:00", "15:00", "16:00"],
    "چهارشنبه": ["10:00", "11:00", "14:00", "15:00", "16:00", "17:00", "18:00"]
}

# --- Main Menu ---
def main_menu():
    keyboard = [
        [InlineKeyboardButton("رزرو جدید", callback_data="new")],
        [InlineKeyboardButton("مشاهده رزرو", callback_data="view")],
        [InlineKeyboardButton("ویرایش اطلاعات", callback_data="edit")],
        [InlineKeyboardButton("لغو رزرو", callback_data="cancel_reserve")]
    ]
    return InlineKeyboardMarkup(keyboard)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("سلام! من بات رزرو جلسات مشاوره هستم. گزینه مورد نظر را انتخاب کنید:", reply_markup=main_menu())

# --- Callback ها ---
async def main_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == "new":
        await query.edit_message_text("لطفاً نام و نام خانوادگی خود را وارد کنید:")
        return NAME
    elif data == "view":
        user_phone = context.user_data.get("phone")
        if not user_phone:
            await query.edit_message_text("ابتدا باید رزرو انجام دهید تا بتوانید مشاهده کنید.", reply_markup=main_menu())
            return ConversationHandler.END
        c.execute("SELECT date, time, link FROM appointments WHERE phone=%s", (user_phone,))
        rows = c.fetchall()
        if rows:
            msg = "\n".join([f"{d} ساعت {t} لینک: {l}" for d, t, l in rows])
        else:
            msg = "رزروی پیدا نشد."
        await query.edit_message_text(msg, reply_markup=main_menu())
        return ConversationHandler.END
    elif data == "edit":
        await query.edit_message_text("لطفاً ابتدا شماره خود را وارد کنید تا اطلاعاتتان بازیابی شود:", reply_markup=None)
        return PHONE
    elif data == "cancel_reserve":
        user_phone = context.user_data.get("phone")
        if not user_phone:
            await query.edit_message_text("ابتدا باید رزرو انجام دهید.", reply_markup=main_menu())
            return ConversationHandler.END
        c.execute("DELETE FROM appointments WHERE phone=%s", (user_phone,))
        conn.commit()
        await query.edit_message_text("رزرو شما لغو شد.", reply_markup=main_menu())
        return ConversationHandler.END

# --- مراحل رزرو ---
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
        if day.weekday() < 5:
            persian_day = ["شنبه","یکشنبه","دوشنبه","سه‌شنبه","چهارشنبه","پنج‌شنبه","جمعه"][day.weekday()]
            dates.append((day.strftime("%Y/%m/%d"), f"{persian_day} {day.strftime('%Y/%m/%d')}"))
    keyboard = [[InlineKeyboardButton(text, callback_data=f"date_{date}")] for date, text in dates]
    await update.message.reply_text("روز مورد نظر را انتخاب کنید:", reply_markup=InlineKeyboardMarkup(keyboard))
    return DATE

async def date_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    selected_date = query.data.split("_")[1]
    context.user_data['date'] = selected_date
    weekday = ["شنبه","یکشنبه","دوشنبه","سه‌شنبه","چهارشنبه","پنج‌شنبه","جمعه"][jdatetime.datetime.strptime(selected_date, "%Y/%m/%d").date().weekday()]
    booked = []
    c.execute("SELECT time FROM appointments WHERE date=%s", (selected_date,))
    booked = [row[0] for row in c.fetchall()]
    free_times = [t for t in AVAILABLE_TIMES[weekday] if t not in booked]
    if not free_times:
        await query.edit_message_text("متاسفانه این روز ظرفیت تکمیل است.", reply_markup=main_menu())
        return ConversationHandler.END
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
              (user['name'], user['phone'], user['age'], user['issue'], "دکتر رضائی", user['date'], selected_time, link))
    conn.commit()
    await query.edit_message_text(f"رزرو شما ثبت شد.\nزمان: {user['date']} - {selected_time}\nلینک: {link}", reply_markup=main_menu())
    await context.bot.send_message(ADMIN_CHAT_ID,
        f"رزرو جدید:\nنام: {user['name']}\nشماره: {user['phone']}\nسن: {user['age']}\nموضوع: {user['issue']}\nروانشناس: دکتر رضائی\nتاریخ: {user['date']}\nساعت: {selected_time}\nلینک: {link}")
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("عملیات لغو شد.", reply_markup=main_menu())
    return ConversationHandler.END

def main():
    app = Application.builder().token(TOKEN).build()
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('start', start)],
        states={
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
    app.add_handler(CallbackQueryHandler(main_callback, pattern="^(new|view|edit|cancel_reserve)$"))
    app.run_polling()

if __name__ == "__main__":
    main()
