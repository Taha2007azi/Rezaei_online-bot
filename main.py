𝙏𝙖𝙃𝙖, [Dec 4, 2025 at 18:24]
psych = context.user_data['psych']
    available_times = PSYCHS[psych].get(weekday_persian, [])
    
    c.execute("SELECT time FROM appointments WHERE date = ? AND psych = ?", (selected_date, psych))
    booked = [row[0] for row in c.fetchall()]
    
    free_times = [t for t in available_times if t not in booked]
    if not free_times:
        await query.edit_message_text("متاسفانه این روز ظرفیت تکمیل است.")
        return ConversationHandler.END

    keyboard = [[InlineKeyboardButton(t, callback_data=f"time_{t}")] for t in free_times]
    
    await query.edit_message_text(
        f"ساعت مورد نظر را انتخاب کنید:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return TIME

async def time_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    selected_time = query.data.split("_")[1]
    context.user_data['time'] = selected_time
    user = context.user_data

    # لینک جلسه
    link = "https://meet.google.com/new"

    c.execute("""INSERT INTO appointments 
                 (name, phone, age, issue, psych, date, time, link, paid) 
                 VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0)""",
              (user['name'], user['phone'], user['age'], user['issue'],
               user['psych'], user['date'], selected_time, link))
    conn.commit()

    # پیام به کاربر
    await query.edit_message_text(
        f"رزرو شما با موفقیت ثبت شد.\n\n"
        f"روانشناس: {user['psych']}\n"
        f"زمان: {user['date']} - {selected_time}\n"
        f"لینک جلسه: {link}"
    )

    # پیام به ادمین
    await context.bot.send_message(
        ADMIN_CHAT_ID,
        f"رزرو جدید ثبت شد:\n\n"
        f"نام: {user['name']}\n"
        f"شماره: {user['phone']}\n"
        f"سن: {user['age']}\n"
        f"موضوع: {user['issue']}\n"
        f"روانشناس: {user['psych']}\n"
        f"تاریخ: {user['date']}\n"
        f"ساعت: {selected_time}\n"
        f"لینک جلسه: {link}"
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

if name == "__main__":
    main()
