import os
import json
import re
from datetime import datetime, timedelta

import httpx
from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message
from sqlalchemy import select

from bot.bot_catalog import BOT_CATALOG
from bot.keyboards import MAIN_MENU, bot_type_confirm, bot_type_menu
from database.db import get_session
from database.models import Bot, BotStatus, User

router = Router(name="create_bot")

TOKEN_RE = re.compile(r"^\d{6,12}:[A-Za-z0-9_-]{30,50}$")
PUBLIC_BASE_URL = os.getenv("PUBLIC_BASE_URL", "https://sizning-domen.uz")


class CreateBotStates(StatesGroup):
    choosing_type = State()
    waiting_token = State()


@router.message(F.text == "➕ Bot yaratish")
async def start_creation(message: Message, state: FSMContext) -> None:
    await state.set_state(CreateBotStates.choosing_type)
    await message.answer(
        "🤖 Quyidagi bot turlaridan birini tanlang:",
        reply_markup=bot_type_menu(),
    )


@router.callback_query(F.data.startswith("bottype:"))
async def show_bot_type_details(callback: CallbackQuery, state: FSMContext) -> None:
    bot_key = callback.data.split(":", 1)[1]
    info = BOT_CATALOG[bot_key]
    await state.update_data(chosen_type=bot_key)

    demo_line = f"\n🎬 Demo bot: @{info.demo_username}" if info.demo_username else ""
    text = (
        f"{info.emoji} <b>{info.title}</b>\n\n"
        f"<i>{info.description}</i>\n"
        f"{demo_line}\n\n"
        f"💵 Yaratish narxi: {info.price:,} so'm\n".replace(",", " ")
        + "💰 Oylik to'lov: tarifga qarab belgilanadi\n"
        + "⚡️ Boshlang'ich bonus: 30 kun"
    )
    await callback.message.edit_text(text, reply_markup=bot_type_confirm(bot_key, info.price))
    await callback.answer()


@router.callback_query(F.data == "back_to_types")
async def back_to_types(callback: CallbackQuery) -> None:
    await callback.message.edit_text(
        "🤖 Quyidagi bot turlaridan birini tanlang:",
        reply_markup=bot_type_menu(),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("confirm_create:"))
async def confirm_create(callback: CallbackQuery, state: FSMContext) -> None:
    bot_key = callback.data.split(":", 1)[1]
    info = BOT_CATALOG[bot_key]

    async with get_session() as session:
        result = await session.execute(
            select(User).where(User.telegram_id == callback.from_user.id)
        )
        user = result.scalar_one_or_none()

    if user is None or user.balance < info.price:
        await callback.message.answer(
            f"⚠️ Balansingizda yetarli mablag' yo'q.\n"
            f"Kerak: {info.price:,} so'm. Joriy balans: {user.balance if user else 0:,} so'm.\n"
            f"💳 Hisob to'ldirish bo'limidan to'ldiring.".replace(",", " "),
            reply_markup=MAIN_MENU,
        )
        await callback.answer()
        return

    await state.update_data(chosen_type=bot_key)
    await state.set_state(CreateBotStates.waiting_token)
    await callback.message.answer(
        "🔑 Endi @BotFather orqali yaratgan botingizning <b>tokenini</b> yuboring.\n\n"
        "Token qanday olinadi:\n"
        "1. @BotFather ga /newbot yuboring\n"
        "2. Bot nomi va username belgilang\n"
        "3. Sizga beriladigan tokenni shu yerga yuboring\n\n"
        "❗️ Tokenni hech kimga bermang — u botingizni to'liq boshqarish huquqini beradi."
    )
    await callback.answer()


@router.message(CreateBotStates.waiting_token)
async def receive_token(message: Message, state: FSMContext) -> None:
    token = message.text.strip() if message.text else ""
    if not TOKEN_RE.match(token):
        await message.answer(
            "❌ Token noto'g'ri formatda. Masalan:\n"
            "<code>123456789:AAHk...xyzABC</code>\n\n"
            "Qaytadan yuboring yoki /cancel bilan bekor qiling."
        )
        return

    data = await state.get_data()
    bot_key = data["chosen_type"]
    info = BOT_CATALOG[bot_key]

    # Tokenni tekshirish uchun getMe chaqiramiz
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(f"https://api.telegram.org/bot{token}/getMe")
        payload = resp.json()

    if not payload.get("ok"):
        await message.answer(
            "❌ Bu token bilan botga ulanib bo'lmadi. Token to'g'riligini tekshirib, "
            "qaytadan yuboring."
        )
        return

    bot_username = payload["result"]["username"]
    bot_display_name = payload["result"]["first_name"]

    async with get_session() as session:
        result = await session.execute(
            select(User).where(User.telegram_id == message.from_user.id)
        )
        user = result.scalar_one()

        new_bot = Bot(
            owner_id=user.id,
            bot_type=bot_key,
            status=BotStatus.ACTIVE,
            bot_token=token,
            bot_username=bot_username,
            display_name=bot_display_name,
            tariff="trial",
            expires_at=datetime.utcnow() + timedelta(days=3),
            settings_json=json.dumps({"owner_telegram_id": message.from_user.id}),
        )
        user.balance -= info.price
        session.add(new_bot)
        await session.flush()
        bot_id = new_bot.id
        await session.commit()

    # Webhook o'rnatish — shu nuqtadan e'tiboran botga kelgan har bir update
    # bizning /webhook/{bot_id} manzilimizga tushadi (bot/runtime.py qarang)
    webhook_url = f"{PUBLIC_BASE_URL}/webhook/{bot_id}"
    async with httpx.AsyncClient(timeout=10) as client:
        await client.get(
            f"https://api.telegram.org/bot{token}/setWebhook",
            params={"url": webhook_url},
        )

    await state.clear()
    await message.answer(
        f"✅ <b>{info.title}</b> muvaffaqiyatli yaratildi!\n\n"
        f"🤖 Bot: @{bot_username}\n"
        f"🎁 3 kunlik BEPUL sinov muddati faollashtirildi.\n"
        f"⏰ Sinov tugagach, botdan foydalanishni davom ettirish uchun "
        f"tarif tanlashingiz kerak bo'ladi (\"Botlarim\" > bot > \"📊 Tarif\").\n\n"
        f"Botni sozlash uchun \"🤖 Botlarim\" bo'limiga o'ting.",
        reply_markup=MAIN_MENU,
    )
