from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ConversationHandler, MessageHandler, filters, ContextTypes
import jdatetime
import sqlite3
import os

# وضعیت‌ها
NAME, PHONE, AGE, ISSUE, PSYCH, DATE, TIME, CANCEL_CODE = range(8)

TOKEN = os.getenv('TOKEN')
ADMIN_USERNAME = "@Taha2007azi"  # فقط عوض نکنی کافیه

conn = sqlite3.connect('appointments.db', check_same_thread=False)
c = conn.cursor()
c.execute('''CREATE TABLE IF NOT EXISTS appointments
             (id INTEGER PRIMARY KEY, name TEXT, phone TEXT, age INTEGER, issue TEXT, psych TEXT, date TEXT, time TEXT, link TEXT, paid INTEGER, code TEXT)''')
conn.commit()

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

# (بقیه توابع مثل قبل هستن تا time_chosen)

async def time_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    selected_time = query.data.split("_")[1]
    context.user_data['time'] = selected_time
    
    user = context.user_data
    link = "https://meet.google.com/new"
    cancel_code = str(hash(f"{user['name']}{selected_time}{user['date']}"))[-6:]  # کد ۶ رقمی منحصر به فرد

    c.execute("""INSERT INTO appointments 
                 (name, phone, age, issue, psych, date, time, link, paid, code) 
                 VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, ?)""",
              (user['name'], user['phone'], user['age'], user['issue'], user['psych'], 
               user['date'], selected_time, link, cancel_code))
    conn.commit()
    
    await query.edit_message_text(
        f"نوبت با موفقیت ثبت شد!\n\n"
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
        print("خطا در نوتیف:", e)
    
    return ConversationHandler.END

# تابع لغو نوبت
async def cancel_appointment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    code = update.message.text.strip()
    c.execute("SELECT * FROM appointments WHERE code = ? AND paid = 0", (code,))
    appointment = c.fetchone()
    
    if appointment:
        c.execute("DELETE FROM appointments WHERE code = ?", (code,))
        conn.commit()
        await update.message.reply_text(f"نوبت با کد `{code}` با موفقیت لغو شد ✅", parse_mode='Markdown')
        
        # اطلاع به ادمین
        try:
            await context.bot.send_message(
                chat_id=ADMIN_USERNAME,
                text=f"لغو نوبت!\n\n"
                     f"نام: {appointment[1]}\n"
                     f"تلفن: {appointment[2]}\n"
                     f"روانشناس: {appointment[5]}\n"
                     f"روز: {appointment[6]} ساعت {appointment[7]}\n"
                     f"توسط کاربر لغو شد."
            )
        except:
            pass
    else:
        await update.message.reply_text("کد لغو اشتباهه یا نوبت قبلاً لغو/پرداخت شده.")
    
    return ConversationHandler.END

def main():
    app = Application.builder().token(TOKEN).build()
    
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('start', start),
                      MessageHandler(filters.TEXT & ~filters.COMMAND, cancel_appointment)],  # لغو با ارسال کد
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
