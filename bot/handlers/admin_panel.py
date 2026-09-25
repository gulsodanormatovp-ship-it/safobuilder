"""
Vezto platformasining SUPERADMIN paneli. Faqat PLATFORM_SUPERADMIN_ID
(.env'dagi sizning shaxsiy Telegram ID'ingiz) ga tegishli chatda ishlaydi
— boshqa hech kim bu buyruqlarni ko'rmaydi va ishlata olmaydi.

Buyruq: /adminpanel
"""
import json
import os

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy import select

from bot.platform_settings import (
    delete_setting, get_effective_catalog, get_setting, set_setting,
)
from database.db import get_session
from database.models import User

router = Router(name="admin_panel")

SUPERADMIN_ID = int(os.getenv("PLATFORM_SUPERADMIN_ID", "0"))


def _is_superadmin(chat_id: int) -> bool:
    return SUPERADMIN_ID != 0 and chat_id == SUPERADMIN_ID


class AdminStates(StatesGroup):
    waiting_card_number = State()
    waiting_card_owner = State()
    waiting_forced_channel = State()
    waiting_price_type = State()
    waiting_price_value = State()
    waiting_balance_id = State()
    waiting_balance_amount = State()
    waiting_broadcast_text = State()
    waiting_new_type_name = State()
    waiting_new_type_emoji = State()
    waiting_new_type_desc = State()
    waiting_new_type_price = State()
    waiting_remove_type = State()


def admin_main_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💳 To'lov kartasi", callback_data="admin:card")],
        [InlineKeyboardButton(text="🔒 Majburiy obuna", callback_data="admin:forcedsub")],
        [InlineKeyboardButton(text="💰 Bot narxlarini o'zgartirish", callback_data="admin:price")],
        [InlineKeyboardButton(text="👤 Foydalanuvchi balansi", callback_data="admin:balance")],
        [InlineKeyboardButton(text="📢 Reklama (hammaga xabar)", callback_data="admin:broadcast")],
        [InlineKeyboardButton(text="➕ Yangi bot turi qo'shish", callback_data="admin:newtype")],
        [InlineKeyboardButton(text="🗑 Bot turini o'chirish/yashirish", callback_data="admin:removetype")],
    ])


@router.message(F.text == "/adminpanel")
async def open_admin_panel(message: Message) -> None:
    if not _is_superadmin(message.from_user.id):
        return  # oddiy foydalanuvchiga hech qanday javob bermaymiz
    await message.answer(
        "👑 <b>Vezto Superadmin Panel</b>\n\nQuyidagilardan birini tanlang:",
        reply_markup=admin_main_menu(),
    )


@router.callback_query(F.data == "admin:back")
async def back_to_admin_menu(callback: CallbackQuery, state: FSMContext) -> None:
    if not _is_superadmin(callback.from_user.id):
        return
    await state.clear()
    await callback.message.edit_text(
        "👑 <b>Vezto Superadmin Panel</b>\n\nQuyidagilardan birini tanlang:",
        reply_markup=admin_main_menu(),
    )
    await callback.answer()


# ---------------- 💳 To'lov kartasi ----------------

@router.callback_query(F.data == "admin:card")
async def card_menu(callback: CallbackQuery) -> None:
    if not _is_superadmin(callback.from_user.id):
        return
    async with get_session() as session:
        number = await get_setting(session, "platform_card_number", "— o'rnatilmagan")
        owner = await get_setting(session, "platform_card_owner", "— o'rnatilmagan")

    await callback.message.edit_text(
        f"💳 <b>Joriy karta:</b>\n\n{number}\n👤 {owner}",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✏️ O'zgartirish", callback_data="admin:card_edit")],
            [InlineKeyboardButton(text="🗑 O'chirish", callback_data="admin:card_delete")],
            [InlineKeyboardButton(text="◀ Orqaga", callback_data="admin:back")],
        ]),
    )
    await callback.answer()


@router.callback_query(F.data == "admin:card_edit")
async def card_edit_start(callback: CallbackQuery, state: FSMContext) -> None:
    if not _is_superadmin(callback.from_user.id):
        return
    await state.set_state(AdminStates.waiting_card_number)
    await callback.message.answer("💳 Yangi karta raqamini yuboring:")
    await callback.answer()


@router.message(AdminStates.waiting_card_number)
async def card_number_received(message: Message, state: FSMContext) -> None:
    if not _is_superadmin(message.from_user.id):
        return
    await state.update_data(card_number=message.text.strip())
    await state.set_state(AdminStates.waiting_card_owner)
    await message.answer("👤 Karta egasining ism-familiyasini yuboring:")


@router.message(AdminStates.waiting_card_owner)
async def card_owner_received(message: Message, state: FSMContext) -> None:
    if not _is_superadmin(message.from_user.id):
        return
    data = await state.get_data()
    async with get_session() as session:
        await set_setting(session, "platform_card_number", data["card_number"])
        await set_setting(session, "platform_card_owner", message.text.strip())
    await state.clear()
    await message.answer("✅ Karta ma'lumotlari yangilandi.", reply_markup=admin_main_menu())


@router.callback_query(F.data == "admin:card_delete")
async def card_delete(callback: CallbackQuery) -> None:
    if not _is_superadmin(callback.from_user.id):
        return
    async with get_session() as session:
        await delete_setting(session, "platform_card_number")
        await delete_setting(session, "platform_card_owner")
    await callback.answer("✅ Karta o'chirildi", show_alert=True)
    await card_menu(callback)


# ---------------- 🔒 Majburiy obuna ----------------

@router.callback_query(F.data == "admin:forcedsub")
async def forced_sub_menu(callback: CallbackQuery) -> None:
    if not _is_superadmin(callback.from_user.id):
        return
    async with get_session() as session:
        channel = await get_setting(session, "platform_forced_channel", "— o'rnatilmagan")

    await callback.message.edit_text(
        f"🔒 <b>Vezto botiga kirishdan oldin majburiy obuna:</b>\n\n{channel}\n\n"
        f"❗️ Bu — Vezto platforma botining o'zi uchun (har bir yaratilgan child bot uchun emas).",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✏️ O'zgartirish", callback_data="admin:forcedsub_edit")],
            [InlineKeyboardButton(text="🗑 O'chirish", callback_data="admin:forcedsub_delete")],
            [InlineKeyboardButton(text="◀ Orqaga", callback_data="admin:back")],
        ]),
    )
    await callback.answer()


@router.callback_query(F.data == "admin:forcedsub_edit")
async def forced_sub_edit_start(callback: CallbackQuery, state: FSMContext) -> None:
    if not _is_superadmin(callback.from_user.id):
        return
    await state.set_state(AdminStates.waiting_forced_channel)
    await callback.message.answer("🔒 Kanal username'ini yuboring (masalan @vezto_channel):")
    await callback.answer()


@router.message(AdminStates.waiting_forced_channel)
async def forced_sub_received(message: Message, state: FSMContext) -> None:
    if not _is_superadmin(message.from_user.id):
        return
    channel = message.text.strip()
    if not channel.startswith("@"):
        await message.answer("❌ Kanal username @ bilan boshlanishi kerak.")
        return
    async with get_session() as session:
        await set_setting(session, "platform_forced_channel", channel)
    await state.clear()
    await message.answer(
        f"✅ Majburiy obuna o'rnatildi: {channel}\n\n"
        f"❗️ Vezto botini shu kanalga admin qilib qo'shishni unutmang.",
        reply_markup=admin_main_menu(),
    )


@router.callback_query(F.data == "admin:forcedsub_delete")
async def forced_sub_delete(callback: CallbackQuery) -> None:
    if not _is_superadmin(callback.from_user.id):
        return
    async with get_session() as session:
        await delete_setting(session, "platform_forced_channel")
    await callback.answer("✅ Majburiy obuna o'chirildi", show_alert=True)
    await forced_sub_menu(callback)


# ---------------- 💰 Bot narxlarini o'zgartirish ----------------

@router.callback_query(F.data == "admin:price")
async def price_menu(callback: CallbackQuery, state: FSMContext) -> None:
    if not _is_superadmin(callback.from_user.id):
        return
    async with get_session() as session:
        catalog = await get_effective_catalog(session)

    rows = [
        [InlineKeyboardButton(
            text=f"{info.emoji} {info.title} — {info.price:,} so'm".replace(",", " "),
            callback_data=f"admin:priceset:{key}",
        )]
        for key, info in catalog.items()
    ]
    rows.append([InlineKeyboardButton(text="◀ Orqaga", callback_data="admin:back")])
    await callback.message.edit_text(
        "💰 <b>Narxni o'zgartirish uchun bot turini tanlang:</b>",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("admin:priceset:"))
async def price_set_start(callback: CallbackQuery, state: FSMContext) -> None:
    if not _is_superadmin(callback.from_user.id):
        return
    type_key = callback.data.split(":", 2)[2]
    await state.update_data(price_type_key=type_key)
    await state.set_state(AdminStates.waiting_price_value)
    await callback.message.answer(f"💰 \"{type_key}\" uchun yangi narxni so'mda yuboring:")
    await callback.answer()


@router.message(AdminStates.waiting_price_value)
async def price_value_received(message: Message, state: FSMContext) -> None:
    if not _is_superadmin(message.from_user.id):
        return
    if not message.text.strip().isdigit():
        await message.answer("❌ Faqat son kiriting.")
        return

    data = await state.get_data()
    type_key = data["price_type_key"]
    new_price = int(message.text.strip())

    async with get_session() as session:
        overrides = json.loads(await get_setting(session, "price_overrides", "{}"))
        overrides[type_key] = new_price
        await set_setting(session, "price_overrides", json.dumps(overrides))

    await state.clear()
    await message.answer(f"✅ Yangi narx saqlandi: {new_price:,} so'm".replace(",", " "), reply_markup=admin_main_menu())


# ---------------- 👤 Foydalanuvchi balansi ----------------

@router.callback_query(F.data == "admin:balance")
async def balance_start(callback: CallbackQuery, state: FSMContext) -> None:
    if not _is_superadmin(callback.from_user.id):
        return
    await state.set_state(AdminStates.waiting_balance_id)
    await callback.message.answer("👤 Foydalanuvchining Telegram ID'sini yuboring:")
    await callback.answer()


@router.message(AdminStates.waiting_balance_id)
async def balance_id_received(message: Message, state: FSMContext) -> None:
    if not _is_superadmin(message.from_user.id):
        return
    if not message.text.strip().isdigit():
        await message.answer("❌ Faqat raqamli ID kiriting.")
        return
    await state.update_data(target_telegram_id=int(message.text.strip()))
    await state.set_state(AdminStates.waiting_balance_amount)
    await message.answer(
        "💰 Miqdorni yuboring. Qo'shish uchun oddiy son (masalan 50000), "
        "ayirish uchun oldiga minus qo'ying (masalan -20000). Max: 50 000 000."
    )


@router.message(AdminStates.waiting_balance_amount)
async def balance_amount_received(message: Message, state: FSMContext) -> None:
    if not _is_superadmin(message.from_user.id):
        return
    text = message.text.strip()
    if not text.lstrip("-").isdigit() or abs(int(text)) > 50_000_000:
        await message.answer("❌ Noto'g'ri format yoki 50 000 000 dan katta.")
        return

    data = await state.get_data()
    target_id = data["target_telegram_id"]
    amount = int(text)

    async with get_session() as session:
        result = await session.execute(select(User).where(User.telegram_id == target_id))
        user = result.scalar_one_or_none()
        if user is None:
            await state.clear()
            await message.answer("❌ Bunday foydalanuvchi topilmadi.", reply_markup=admin_main_menu())
            return
        user.balance += amount
        new_balance = user.balance
        await session.commit()

    await state.clear()
    await message.answer(
        f"✅ Bajarildi. {target_id} ning yangi balansi: {new_balance:,} so'm".replace(",", " "),
        reply_markup=admin_main_menu(),
    )


# ---------------- 📢 Reklama (barcha foydalanuvchilarga) ----------------

@router.callback_query(F.data == "admin:broadcast")
async def broadcast_start(callback: CallbackQuery, state: FSMContext) -> None:
    if not _is_superadmin(callback.from_user.id):
        return
    await state.set_state(AdminStates.waiting_broadcast_text)
    await callback.message.answer("📢 Barcha Vezto foydalanuvchilariga yuboriladigan xabarni yozing:")
    await callback.answer()


@router.message(AdminStates.waiting_broadcast_text)
async def broadcast_text_received(message: Message, state: FSMContext) -> None:
    if not _is_superadmin(message.from_user.id):
        return

    text = message.text
    async with get_session() as session:
        result = await session.execute(select(User))
        users = result.scalars().all()

    sent = 0
    for user in users:
        try:
            await message.bot.send_message(user.telegram_id, text)
            sent += 1
        except Exception:
            pass

    await state.clear()
    await message.answer(f"✅ Xabar {sent} ta foydalanuvchiga yuborildi.", reply_markup=admin_main_menu())


# ---------------- ➕ Yangi bot turi qo'shish (faqat metadata) ----------------

@router.callback_query(F.data == "admin:newtype")
async def new_type_start(callback: CallbackQuery, state: FSMContext) -> None:
    if not _is_superadmin(callback.from_user.id):
        return
    await state.set_state(AdminStates.waiting_new_type_name)
    await callback.message.answer(
        "➕ <b>Yangi bot turi qo'shish</b>\n\n"
        "❗️ Bu yerda faqat NOM, NARX va TAVSIFni kiritasiz — bot \"Bot yaratish\" "
        "menyusida darhol ko'rinadi. Lekin uning ICHKI MANTIG'I (qanday ishlashi) "
        "hali yozilmagan bo'ladi — buni menga alohida tasvirlab bering, men "
        "kodini yozib beraman, shundan keyingina bot to'liq ishlaydi.\n\n"
        "Bot nomini yuboring (masalan: Onlayn Kutubxona Bot):"
    )
    await callback.answer()


@router.message(AdminStates.waiting_new_type_name)
async def new_type_name_received(message: Message, state: FSMContext) -> None:
    if not _is_superadmin(message.from_user.id):
        return
    await state.update_data(new_type_title=message.text.strip())
    await state.set_state(AdminStates.waiting_new_type_emoji)
    await message.answer("🎨 Bitta emoji yuboring (masalan 📚):")


@router.message(AdminStates.waiting_new_type_emoji)
async def new_type_emoji_received(message: Message, state: FSMContext) -> None:
    if not _is_superadmin(message.from_user.id):
        return
    await state.update_data(new_type_emoji=message.text.strip())
    await state.set_state(AdminStates.waiting_new_type_desc)
    await message.answer("📝 Qisqa tavsif yuboring:")


@router.message(AdminStates.waiting_new_type_desc)
async def new_type_desc_received(message: Message, state: FSMContext) -> None:
    if not _is_superadmin(message.from_user.id):
        return
    await state.update_data(new_type_desc=message.text.strip())
    await state.set_state(AdminStates.waiting_new_type_price)
    await message.answer("💰 Yaratish narxini so'mda yuboring:")


@router.message(AdminStates.waiting_new_type_price)
async def new_type_price_received(message: Message, state: FSMContext) -> None:
    if not _is_superadmin(message.from_user.id):
        return
    if not message.text.strip().isdigit():
        await message.answer("❌ Faqat son kiriting.")
        return

    data = await state.get_data()
    type_key = data["new_type_title"].lower().replace(" ", "_")[:32]

    new_entry = {
        "key": type_key,
        "title": data["new_type_title"],
        "emoji": data["new_type_emoji"],
        "description": data["new_type_desc"],
        "price": int(message.text.strip()),
    }

    async with get_session() as session:
        custom_types = json.loads(await get_setting(session, "custom_bot_types", "[]"))
        custom_types.append(new_entry)
        await set_setting(session, "custom_bot_types", json.dumps(custom_types))

    await state.clear()
    await message.answer(
        f"✅ \"{new_entry['title']}\" \"Bot yaratish\" menyusida ko'rina boshladi.\n\n"
        f"⚠️ Eslatma: hali mantiqi yozilmagan — foydalanuvchi tanlasa, "
        f"\"tez orada tayyor bo'ladi\" degan xabar ko'radi, to'lov yechilmaydi.\n\n"
        f"Bot turi kaliti: <code>{type_key}</code> — menga uning qanday ishlashi "
        f"kerakligini tasvirlab bering, men shu kalit bilan kod yozib beraman.",
        reply_markup=admin_main_menu(),
    )


# ---------------- 🗑 Bot turini o'chirish/yashirish ----------------

@router.callback_query(F.data == "admin:removetype")
async def remove_type_menu(callback: CallbackQuery) -> None:
    if not _is_superadmin(callback.from_user.id):
        return
    async with get_session() as session:
        catalog = await get_effective_catalog(session)

    rows = [
        [InlineKeyboardButton(text=f"{info.emoji} {info.title}", callback_data=f"admin:hide:{key}")]
        for key, info in catalog.items()
    ]
    rows.append([InlineKeyboardButton(text="◀ Orqaga", callback_data="admin:back")])
    await callback.message.edit_text(
        "🗑 <b>Qaysi turni \"Bot yaratish\" menyusidan yashirmoqchisiz?</b>\n\n"
        "(Bu allaqachon yaratilgan botlarga ta'sir qilmaydi — faqat yangi yaratishni to'xtatadi)",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("admin:hide:"))
async def hide_type(callback: CallbackQuery) -> None:
    if not _is_superadmin(callback.from_user.id):
        return
    type_key = callback.data.split(":", 2)[2]

    async with get_session() as session:
        hidden = json.loads(await get_setting(session, "hidden_types", "[]"))
        if type_key not in hidden:
            hidden.append(type_key)
        await set_setting(session, "hidden_types", json.dumps(hidden))

    await callback.answer(f"✅ \"{type_key}\" yashirildi", show_alert=True)
    await remove_type_menu(callback)
