from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ConversationHandler, MessageHandler, filters, ContextTypes
import sqlite3
import os

# وضعیت‌های مکالمه
START_MENU, NAME_INPUT, PHONE_INPUT = range(3)

# توکن از Environment
TOKEN = os.getenv('TOKEN')

# آیدی ادمین
ADMIN_CHAT_ID = 7548579249  # این را با آیدی خودت عوض کن

# اتصال به دیتابیس
conn = sqlite3.connect('appointments.db', check_same_thread=False)
c = conn.cursor()
c.execute('''CREATE TABLE IF NOT EXISTS appointments
             (id INTEGER PRIMARY KEY, name TEXT, phone TEXT)''')
conn.commit()

# --- START ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("شروع", callback_data='start')],
        [InlineKeyboardButton("چک کردن رزرو فعلی", callback_data='check')],
        [InlineKeyboardButton("لغو", callback_data='cancel')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "سلام! گزینه مورد نظر را انتخاب کنید:",
        reply_markup=reply_markup
    )
    return START_MENU

async def menu_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.data == 'start':
        await query.edit_message_text("لطفاً نام خود را وارد کنید:")
        return NAME_INPUT
    elif query.data == 'check':
        c.execute("SELECT name, phone FROM appointments")
        rows = c.fetchall()
        if rows:
            msg = "رزروهای فعلی:\n" + "\n".join([f"{name} - {phone}" for name, phone in rows])
        else:
            msg = "رزروی ثبت نشده است."
        await query.edit_message_text(msg)
        return START_MENU
    elif query.data == 'cancel':
        await query.edit_message_text("عملیات لغو شد.")
        return ConversationHandler.END

async def name_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['name'] = update.message.text
    await update.message.reply_text("شماره تماس خود را وارد کنید:")
    return PHONE_INPUT

async def phone_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['phone'] = update.message.text
    user = context.user_data
    c.execute("INSERT INTO appointments (name, phone) VALUES (?, ?)", (user['name'], user['phone']))
    conn.commit()
    
    # پیام به کاربر
    await update.message.reply_text(f"رزرو شما ثبت شد:\nنام: {user['name']}\nشماره: {user['phone']}")
    
    # پیام به ادمین
    await context.bot.send_message(
        ADMIN_CHAT_ID,
        f"رزرو جدید:\nنام: {user['name']}\nشماره: {user['phone']}"
    )
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("عملیات لغو شد.")
    return ConversationHandler.END

def main():
    app = Application.builder().token(TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('start', start)],
        states={
            START_MENU: [CallbackQueryHandler(menu_choice)],
            NAME_INPUT: [MessageHandler(filters.TEXT & ~filters.COMMAND, name_input)],
            PHONE_INPUT: [MessageHandler(filters.TEXT & ~filters.COMMAND, phone_input)],
        },
        fallbacks=[CommandHandler('cancel', cancel)]
    )

    app.add_handler(conv_handler)
    app.run_polling()

if __name__ == "__main__":
    main()
