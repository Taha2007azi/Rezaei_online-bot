from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ConversationHandler, MessageHandler, filters, ContextTypes
import jdatetime
from datetime import datetime, timedelta
import sqlite3
import os
import os

# وضعیت‌های مکالمه
NAME, PHONE, AGE, ISSUE, PSYCH, DATE, TIME = range(7)

# توکن رو از Environment Variable بگیر
TOKEN = os.getenv('TOKEN')

# اتصال به دیتابیس
conn = sqlite3.connect('appointments.db', check_same_thread=False)
c = conn.cursor()
c.execute('''CREATE TABLE IF NOT EXISTS appointments
             (id INTEGER PRIMARY KEY, name TEXT, phone TEXT, age INTEGER, issue TEXT, psych TEXT, date TEXT, time TEXT, link TEXT, paid INTEGER)''')
conn.commit()

# روانشناس‌ها و ساعت‌های کاری (بعداً خودت تغییر بده)
PSYCHS = {
    "دکتر محمدی": {"شنبه": ["10:00", "11:00", "14:00", "15:00", "16:00", "17:00", "18:00"],
                  "یکشنبه": ["10:00", "11:00", "14:00", "15:00", "16:00", "17:00", "18:00"],
                  "دوشنبه": ["10:00", "11:00", "14:00", "15:00", "16:00", "17:00"],
                  "سه‌شنبه": ["10:00", "11:00", "14:00", "15:00", "16:00"],
                  "چهارشنبه": ["10:00", "11:00", "14:00", "15:00", "16:00", "17:00", "18:00"]}
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
    
    # نمایش روزهای هفته جاری و هفته بعد
    today = jdatetime.date.today()
    dates = []
    for i in range(14):
        day = today + jdatetime.timedelta(days=i)
        if day.weekday() < 5:  # فقط شنبه تا چهارشنبه
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
    
    jalali = jdatetime.datetime.strptime(selected_date, "%Y/%m/%d").date()
    weekday_persian = ["شنبه", "یکشنبه", "دوشنبه", "سه‌شنبه", "چهارشنبه", "پنج‌شنبه", "جمعه"][jalali.weekday()]
    psych = context.user_data['psych']
    
    available_times = PSYCHS[psych].get(weekday_persian, [])
    
    # حذف ساعت‌های رزرو شده
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
    link = f"https://meet.google.com/new?authuser=0"  # یا لینک ثابت زوم
    
    # ذخیره در دیتابیس
    c.execute("""INSERT INTO appointments 
                 (name, phone, age, issue, psych, date, time, link, paid) 
                 VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0)""",
              (user['name'], user['phone'], user['age'], user['issue'], user['psych'], 
               user['date'], selected_time, link))
    conn.commit()
    
    await query.edit_message_text(
        f"✅ نوبت با موفقیت ثبت شد!\n\n"
        f"روانشناس: {user['psych']}\n"
        f"روز: {user['date']} ساعت {selected_time}\n"
        f"لینک جلسه: {link}\n\n"
        f"هزینه جلسه: ۶۰۰٬۰۰۰ تومان\n"
        f"لینک پرداخت ارسال می‌شه..."
    )
    
    # اینجا لینک پرداخت زرین‌پال می‌فرستیم (بعداً اضافه می‌کنم)
    
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("عملیات لغو شد. دوباره /start بزنید.")
    return ConversationHandler.END

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

if __name__ == '__main__':
    main()
