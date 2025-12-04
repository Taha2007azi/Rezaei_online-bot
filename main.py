from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, ConversationHandler, filters, ContextTypes
)
import jdatetime
import psycopg2
import os
from urllib.parse import urlparse

# وضعیت‌های مکالمه
NAME, PHONE, AGE, ISSUE, DATE, TIME = range(6)

# توکن بات و ادمین
TOKEN = os.getenv('TOKEN')
ADMIN_CHAT_ID = 7548579249

# اتصال به PostgreSQL
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

# ایجاد جدول اگر وجود ندارد
c.execute('''
CREATE TABLE IF NOT EXISTS appointments (
    id SERIAL PRIMARY KEY,
    chat_id BIGINT,
    name TEXT,
    phone TEXT,
    age INTEGER,
    issue TEXT,
    date TEXT,
    time TEXT,
    link TEXT,
    paid INTEGER
)
''')
conn.commit()

# ساعات کاری دکتر رضائی
PSYCHS = {
    "دکتر رضائی": {
        "شنبه": ["10:00","11:00","14:00","15:00","16:00","17:00","18:00"],
        "یکشنبه": ["10:00","11:00","14:00","15:00","16:00","17:00","18:00"],
        "دوشنبه": ["10:00","11:00","14:00","15:00","16:00","17:00"],
        "سه‌شنبه": ["10:00","11:00","14:00","15:00","16:00"],
        "چهارشنبه": ["10:00","11:00","14:00","15:00","16:00","17:00","18:00"]
    }
}

# --- منوی اصلی ---
def main_menu():
    keyboard = [
        [InlineKeyboardButton("رزرو جدید", callback_data="new_appointment")],
        [InlineKeyboardButton("مشاهده رزروها", callback_data="view_appointments")],
        [InlineKeyboardButton("ویرایش اطلاعات", callback_data="edit_info")],
        [InlineKeyboardButton("لغو رزرو", callback_data="cancel_appointment")]
    ]
    return InlineKeyboardMarkup(keyboard)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "سلام! خوش آمدید. لطفاً یکی از گزینه‌های زیر را انتخاب کنید:",
        reply_markup=main_menu()
    )

# --- Callback ها ---
async def menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    chat_id = query.message.chat_id
    context.user_data['chat_id'] = chat_id

    if data == "new_appointment":
        await query.edit_message_text("لطفاً نام و نام خانوادگی خود را وارد کنید:")
        return NAME

    elif data == "view_appointments":
        c.execute("SELECT name, phone, date, time FROM appointments WHERE chat_id=%s", (chat_id,))
        rows = c.fetchall()
        if rows:
            msg = "\n".join([f"{name} - {phone} - {date} {time}" for name, phone, date, time in rows])
        else:
            msg = "هیچ رزروی ثبت نشده است."
        await query.edit_message_text(msg, reply_markup=main_menu())
        return ConversationHandler.END

    elif data == "edit_info":
        keyboard = [
            [InlineKeyboardButton("تغییر نام", callback_data="edit_name")],
            [InlineKeyboardButton("تغییر شماره", callback_data="edit_phone")]
        ]
        await query.edit_message_text("کدام یک را می‌خواهید تغییر دهید؟", reply_markup=InlineKeyboardMarkup(keyboard))
        return ConversationHandler.END

    elif data == "cancel_appointment":
        c.execute("DELETE FROM appointments WHERE chat_id=%s", (chat_id,))
        conn.commit()
        await query.edit_message_text("تمام رزروهای شما لغو شد.", reply_markup=main_menu())
        return ConversationHandler.END

# --- رزرو ---
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
    # آماده کردن تاریخ‌ها
    today = jdatetime.date.today()
    dates = []
    for i in range(14):
        day = today + jdatetime.timedelta(days=i)
        if day.weekday() < 5:
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
    available_times = PSYCHS["دکتر رضائی"].get(weekday_persian, [])
    c.execute("SELECT time FROM appointments WHERE date=%s AND chat_id=%s", (selected_date, context.user_data['chat_id']))
    booked = [row[0] for row in c.fetchall()]
    free_times = [t for t in available_times if t not in booked]
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
    user = context.user_data
    link = "https://meet.google.com/new"
    c.execute("""INSERT INTO appointments (chat_id,name,phone,age,issue,date,time,link,paid)
                 VALUES (%s,%s,%s,%s,%s,%s,%s,%s,0)""",
              (user['chat_id'], user['name'], user['phone'], user['age'], user['issue'],
               user['date'], selected_time, link))
    conn.commit()
    await query.edit_message_text(
        f"رزرو شما با موفقیت ثبت شد.\nزمان: {user['date']} - {selected_time}\nلینک جلسه: {link}",
        reply_markup=main_menu()
    )
    await context.bot.send_message(
        ADMIN_CHAT_ID,
        f"رزرو جدید ثبت شد:\nنام: {user['name']}\nشماره: {user['phone']}\nسن: {user['age']}\nموضوع: {user['issue']}\nتاریخ: {user['date']}\nساعت: {selected_time}\nلینک جلسه: {link}"
    )
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("عملیات لغو شد.", reply_markup=main_menu())
    return ConversationHandler.END

# --- Main ---
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
            TIME: [CallbackQueryHandler(time_chosen)]
        },
        fallbacks=[CommandHandler('cancel', cancel)]
    )

    app.add_handler(conv_handler)
    # منوی اصلی Callback
    app.add_handler(CallbackQueryHandler(menu_handler, pattern="^(new_appointment|view_appointments|edit_info|cancel_appointment)$"))
    app.run_polling()

if __name__ == "__main__":
    main()
