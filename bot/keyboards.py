from aiogram.types import (
    InlineKeyboardButton, InlineKeyboardMarkup,
    KeyboardButton, ReplyKeyboardMarkup,
)

WEBAPP_BASE_URL = "https://sizning-domen.uz/webapp"

# ---- Asosiy menyu (screenshotlardagi 8 tugmali reply-klaviatura) ----
MAIN_MENU = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="➕ Bot yaratish"), KeyboardButton(text="🤖 Botlarim")],
        [KeyboardButton(text="🗣 Referal"), KeyboardButton(text="📱 Shaxsiy kabinet")],
        [KeyboardButton(text="🌐 Saytga kirish"), KeyboardButton(text="💳 Hisob to'ldirish")],
        [KeyboardButton(text="📩 Murojaat"), KeyboardButton(text="📚 Qo'llanma")],
    ],
    resize_keyboard=True,
)


def bot_type_menu(catalog: dict) -> InlineKeyboardMarkup:
    """
    `catalog` — {key: BotTypeInfo} lug'ati (platform_settings.get_effective_catalog
    orqali olinadi, admin panelda o'zgartirilgan narx/turlarni ham o'z ichiga oladi).
    """
    rows, row = [], []
    for i, (key, info) in enumerate(catalog.items(), start=1):
        row.append(InlineKeyboardButton(text=f"{info.emoji} {info.title}", callback_data=f"bottype:{key}"))
        if i % 2 == 0:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    return InlineKeyboardMarkup(inline_keyboard=rows)


def bot_type_confirm(bot_type: str, price: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💳 Tariflar ro'yxati", callback_data=f"tariffs:{bot_type}")],
        [InlineKeyboardButton(text=f"✅ Bot yaratish — {price:,} so'm".replace(",", " "),
                               callback_data=f"confirm_create:{bot_type}")],
        [InlineKeyboardButton(text="◀ Orqaga", callback_data="back_to_types")],
    ])


def payment_methods_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔵 Click (Avto)", callback_data="pay:click"),
         InlineKeyboardButton(text="💳 Payme (Avto)", callback_data="pay:payme")],
        [InlineKeyboardButton(text="🟢 Paynet (Avto)", callback_data="pay:paynet")],
        [InlineKeyboardButton(text="💵 Naqd pul orqali (Paynet bankomat)", callback_data="pay:paynet_cash")],
        [InlineKeyboardButton(text="💳 Karta orqali (chek bilan)", callback_data="pay:card_manual")],
    ])


def admin_payment_review(payment_id: int) -> InlineKeyboardMarkup:
    """To'lov chekini tasdiqlash uchun admin guruhiga yuboriladigan tugmalar."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Tasdiqlash", callback_data=f"admin_approve:{payment_id}"),
         InlineKeyboardButton(text="❌ Rad etish", callback_data=f"admin_reject:{payment_id}")],
    ])


def my_bots_menu(bots: list[tuple[int, str, str]]) -> InlineKeyboardMarkup:
    """bots: [(bot_id, display_name, status_emoji), ...]"""
    rows = [
        [InlineKeyboardButton(text=f"{status} @{name}", callback_data=f"managebot:{bot_id}")]
        for bot_id, name, status in bots
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def bot_manage_menu(bot_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⚙️ Sozlash", callback_data=f"botsettings:{bot_id}")],
        [InlineKeyboardButton(text="👤 Profil (nom, rasm)", callback_data=f"botprofile:{bot_id}")],
        [InlineKeyboardButton(text="📊 Tarif", callback_data=f"bottariff:{bot_id}")],
        [InlineKeyboardButton(text="💰 To'lov", callback_data=f"bottopup:{bot_id}")],
        [InlineKeyboardButton(
            text="📈 Statistika (Web App)",
            web_app={"url": f"{WEBAPP_BASE_URL}?mode=admin&bot_id={bot_id}"},
        )],
        [InlineKeyboardButton(text="◀ Orqaga", callback_data="my_bots"),
         InlineKeyboardButton(text="🗑 O'chirish", callback_data=f"botdelete:{bot_id}")],
    ])


def help_center_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❓ FAQ", callback_data="help:faq")],
        [InlineKeyboardButton(text="🛠 Muammo haqida yozish", callback_data="help:report")],
        [InlineKeyboardButton(text="📞 Admin bilan bog'lanish", callback_data="help:admin")],
    ])
