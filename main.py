import os
import psycopg2
from urllib.parse import urlparse
from telegram import (
    Update, 
    ReplyKeyboardMarkup, 
    KeyboardButton
)
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ConversationHandler,
    filters,
    ContextTypes
)


# ============================
#   READ ENV VARIABLES
# ============================
TOKEN = os.getenv("TOKEN")
DATABASE_URL = os.getenv("DATABASE_URL")

print("Starting bot...")
print("TOKEN:", TOKEN)
print("DATABASE_URL:", DATABASE_URL)

conn = None
c = None

# ============================
#   CONNECT DATABASE SAFELY
# ============================
if DATABASE_URL:
    try:
        print("Connecting to DB...")
        url = urlparse(DATABASE_URL)
        conn = psycopg2.connect(
            dbname=url.path[1:], user=url.username,
            password=url.password, host=url.hostname, port=url.port
        )
        c = conn.cursor()
        print("DB connected!")

        # create table if not exist
        c.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id BIGINT PRIMARY KEY,
                name TEXT,
                phone TEXT,
                appointment TEXT
            );
        """)
        conn.commit()

    except Exception as e:
        print("DB error:", e)
        conn = None
        c = None
else:
    print("DATABASE_URL not set. Running without DB.")
    conn = None
    c = None


# ============================
#   STATES
# ============================
NAME, PHONE, CHANGE_NAME, CHANGE_PHONE, SET_APPOINTMENT = range(5)


# ============================
#   KEYBOARD (PRO PANEL)
# ============================
def main_keyboard():
    return ReplyKeyboardMarkup(
        [
            ["رزرو وقت مشاوره"],
            ["ویرایش نام", "ویرایش شماره"],
            ["مشاهده اطلاعات", "انصراف"],
        ],
        resize_keyboard=True
    )


# ============================
#   COMMAND: /start
# ============================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id

    # If DB is available, load data
    if c:
        c.execute("SELECT name, phone, appointment FROM users WHERE id=%s", (user_id,))
        result = c.fetchone()
    else:
        result = None

    if result:
        text = f"""
سلام {result[0]} عزیز.
این منوی شخصی شماست.

نام: {result[0]}
شماره: {result[1]}
زمان وقت: {result[2] if result[2] else "ثبت نشده"}
"""
    else:
        text = "سلام. لطفاً نام خود را وارد کنید."

    await update.message.reply_text(text, reply_markup=main_keyboard())
    return NAME if not result else ConversationHandler.END


# ============================
#   STEP 1: SET NAME
# ============================
async def set_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    name = update.message.text
    context.user_data["name"] = name
    await update.message.reply_text("شماره تماس خود را وارد کنید:")
    return PHONE


# ============================
#   STEP 2: SET PHONE
# ============================
async def set_phone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    phone = update.message.text
    name = context.user_data["name"]
    user_id = update.message.from_user.id

    if c:
        c.execute(
            "INSERT INTO users (id, name, phone) VALUES (%s, %s, %s) ON CONFLICT (id) DO UPDATE SET name=%s, phone=%s",
            (user_id, name, phone, name, phone)
        )
        conn.commit()

    await update.message.reply_text("ثبت شد.", reply_markup=main_keyboard())
    return ConversationHandler.END


# ============================
#   EDIT NAME
# ============================
async def edit_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("نام جدید را وارد کنید:")
    return CHANGE_NAME

async def save_new_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    new_name = update.message.text
    user_id = update.message.from_user.id

    if c:
        c.execute("UPDATE users SET name=%s WHERE id=%s", (new_name, user_id))
        conn.commit()

    await update.message.reply_text("نام جدید ثبت شد.", reply_markup=main_keyboard())
    return ConversationHandler.END


# ============================
#   EDIT PHONE
# ============================
async def edit_phone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("شماره جدید را وارد کنید:")
    return CHANGE_PHONE

async def save_new_phone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    new_phone = update.message.text
    user_id = update.message.from_user.id

    if c:
        c.execute("UPDATE users SET phone=%s WHERE id=%s", (new_phone, user_id))
        conn.commit()

    await update.message.reply_text("شماره جدید ثبت شد.", reply_markup=main_keyboard())
    return ConversationHandler.END


# ============================
#   APPOINTMENT
# ============================
async def appointment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("لطفاً زمان موردنظر را وارد کنید:")
    return SET_APPOINTMENT

async def save_appointment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    time = update.message.text
    user_id = update.message.from_user.id

    if c:
        c.execute("UPDATE users SET appointment=%s WHERE id=%s", (time, user_id))
        conn.commit()

    await update.message.reply_text("زمان ملاقات ثبت شد.", reply_markup=main_keyboard())
    return ConversationHandler.END


# ============================
#   SHOW INFO
# ============================
async def show_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id

    if c:
        c.execute("SELECT name, phone, appointment FROM users WHERE id=%s", (user_id,))
        r = c.fetchone()
    else:
        r = None

    if not r:
        await update.message.reply_text("اطلاعاتی ثبت نشده.")
    else:
        msg = f"""
نام: {r[0]}
شماره: {r[1]}
زمان ملاقات: {r[2] if r[2] else "ثبت نشده"}
"""
        await update.message.reply_text(msg)

# ============================
#   CANCEL
# ============================
async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id

    if c:
        c.execute("DELETE FROM users WHERE id=%s", (user_id,))
        conn.commit()

    await update.message.reply_text("تمام اطلاعات حذف شد.", reply_markup=main_keyboard())
    return ConversationHandler.END


# ============================
#   MAIN
# ============================
def main():
    app = ApplicationBuilder().token(TOKEN).build()

    conv = ConversationHandler(
        entry_points=[CommandHandler("start", start)],

        states={
            NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, set_name)],
            PHONE: [MessageHandler(filters.TEXT & ~filters.COMMAND, set_phone)],
            CHANGE_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, save_new_name)],
            CHANGE_PHONE: [MessageHandler(filters.TEXT & ~filters.COMMAND, save_new_phone)],
            SET_APPOINTMENT: [MessageHandler(filters.TEXT & ~filters.COMMAND, save_appointment)],
        },

        fallbacks=[CommandHandler("cancel", cancel)],
    )

    app.add_handler(conv)

    app.add_handler(MessageHandler(filters.Regex("رزرو وقت مشاوره"), appointment))
    app.add_handler(MessageHandler(filters.Regex("ویرایش نام"), edit_name))
    app.add_handler(MessageHandler(filters.Regex("ویرایش شماره"), edit_phone))
    app.add_handler(MessageHandler(filters.Regex("مشاهده اطلاعات"), show_info))
    app.add_handler(MessageHandler(filters.Regex("انصراف"), cancel))

    print("Bot is running...")
    app.run_polling()


if __name__ == "__main__":
    main()
