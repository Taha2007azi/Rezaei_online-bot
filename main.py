𝙏𝙖𝙃𝙖, [Dec 4, 2025 at 23:07]
sub(r"\D", "", normalize_digits(text))
    return len(digits) in (10, 11)

def valid_age(text: str) -> bool:
    digits = normalize_digits(text).strip()
    return digits.isdigit() and 1 <= int(digits) <= 120


# -------------------------
# تقویم و منو
# -------------------------
def render_month_keyboard(year: int, month: int):
    first_day = jdatetime.date(year, month, 1)
    days_in_month = jdatetime.j_days_in_month[month - 1]
    start_offset = (first_day.weekday() + 2) % 7

    buttons = []
    buttons.append([
        InlineKeyboardButton("◀️", callback_data=f"cal:prev:{year}:{month}"),
        InlineKeyboardButton(f"{first_day.j_months_fa[month-1]} {year}", callback_data="noop"),
        InlineKeyboardButton("▶️", callback_data=f"cal:next:{year}:{month}"),
    ])
    buttons.append([InlineKeyboardButton(d, callback_data="noop") for d in ["ش", "ی", "د", "س", "چ", "پ", "ج"]])

    week = [None] * 7
    day = 1
    for i in range(start_offset, 7):
        week[i] = day
        day += 1
    buttons.append([
        InlineKeyboardButton(" " if d is None else str(d),
                             callback_data="noop" if d is None else f"cal:day:{year}:{month:02d}:{d:02d}")
        for d in week
    ])

    while day <= days_in_month:
        week = []
        for _ in range(7):
            if day <= days_in_month:
                week.append(day)
                day += 1
            else:
                week.append(None)
        buttons.append([
            InlineKeyboardButton(" " if d is None else str(d),
                                 callback_data="noop" if d is None else f"cal:day:{year}:{month:02d}:{d:02d}")
            for d in week
        ])

    buttons.append([
        InlineKeyboardButton("امروز", callback_data="cal:today"),
        InlineKeyboardButton("بستن", callback_data="cal:close"),
    ])
    return InlineKeyboardMarkup(buttons)


def main_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("رزرو جدید", callback_data="menu:new")],
        [InlineKeyboardButton("مشاهده رزرو", callback_data="menu:view"),
         InlineKeyboardButton("ویرایش اطلاعات", callback_data="menu:edit")],
        [InlineKeyboardButton("انصراف (حذف رزرو)", callback_data="menu:cancel")],
    ])


# -------------------------
# هندلرها
# -------------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = "سلام! به ربات رزرو مشاوره روانشناسی خوش آمدید\nلطفاً از منوی زیر استفاده کنید:"
    if update.message:
        await update.message.reply_text(text, reply_markup=main_menu())
    else:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text(text, reply_markup=main_menu())


async def menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    chat_id = query.from_user.id

    if data == "menu:new":
        user_info = None
        if _cursor:
            rows = await db_execute("SELECT name, phone, age FROM appointments WHERE chat_id=%s", (chat_id,), fetch=True)
            if rows and rows[0]['name']:
                user_info = rows[0]

        if user_info:
            await query.edit_message_text(
                f"نام فعلی: {user_info['name']}\n\nاگر می‌خواهید تغییر دهید نام جدید بفرستید.\nدر غیر این صورت همین نام را دوباره ارسال کنید.",
                reply_markup=None
            )
        else:
            await query.edit_message_text("لطفاً نام و نام خانوادگی خود را وارد کنید:", reply_markup=None)
        return NAME

    elif data == "menu:view":
        appt = None
        if _cursor:
            rows = await db_execute("SELECT * FROM appointments WHERE chat_id=%s", (chat_id,), fetch=True)
            appt = rows[0] if rows else None
        else:
            appt = _memory_appointments.get(chat_id)

        if not appt:
            await query.edit_message_text("شما هنوز رزرو ندارید.", reply_markup=main_menu())
            return ConversationHandler.END

        msg = (
            f"رزرو شما:\n\n"
