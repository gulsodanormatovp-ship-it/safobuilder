import json
from datetime import datetime, timedelta

import httpx
from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy import select

from bot.tariffs import TARIFFS
from database.db import get_session
from database.models import Bot, User

router = Router(name="bot_settings")


class ProfileStates(StatesGroup):
    waiting_name = State()
    waiting_description = State()


class SettingsStates(StatesGroup):
    waiting_taxi_group = State()
    waiting_anketa_questions = State()


# ------------------------------------------------------------------
# 👤 Profil (nom, tavsif) — haqiqiy Telegram Bot API orqali o'zgartiriladi
# ------------------------------------------------------------------

@router.callback_query(F.data.startswith("botprofile:"))
async def profile_menu(callback: CallbackQuery, state: FSMContext) -> None:
    bot_id = int(callback.data.split(":", 1)[1])
    await state.update_data(bot_id=bot_id)
    await state.set_state(ProfileStates.waiting_name)
    await callback.message.answer(
        "✏️ Botingiz uchun yangi <b>nom</b> yuboring (masalan: Kino Olami).\n"
        "O'zgartirmoqchi bo'lmasangiz /skip yozing."
    )
    await callback.answer()


@router.message(ProfileStates.waiting_name)
async def set_profile_name(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    bot_id = data["bot_id"]

    if message.text.strip() != "/skip":
        async with get_session() as session:
            result = await session.execute(select(Bot).where(Bot.id == bot_id))
            bot_row = result.scalar_one()
            token = bot_row.bot_token

        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                f"https://api.telegram.org/bot{token}/setMyName",
                json={"name": message.text.strip()[:64]},
            )
            ok = resp.json().get("ok")

        async with get_session() as session:
            result = await session.execute(select(Bot).where(Bot.id == bot_id))
            bot_row = result.scalar_one()
            if ok:
                bot_row.display_name = message.text.strip()[:64]
            await session.commit()

        await message.answer("✅ Nom yangilandi!" if ok else "❌ Nomni yangilab bo'lmadi.")

    await state.set_state(ProfileStates.waiting_description)
    await message.answer(
        "📝 Endi botingiz uchun <b>tavsif</b> yuboring (foydalanuvchilar botni "
        "ochganda ko'radigan matn). O'tkazib yuborish uchun /skip yozing."
    )


@router.message(ProfileStates.waiting_description)
async def set_profile_description(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    bot_id = data["bot_id"]

    if message.text.strip() != "/skip":
        async with get_session() as session:
            result = await session.execute(select(Bot).where(Bot.id == bot_id))
            bot_row = result.scalar_one()
            token = bot_row.bot_token

        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                f"https://api.telegram.org/bot{token}/setMyDescription",
                json={"description": message.text.strip()[:512]},
            )
            ok = resp.json().get("ok")

        await message.answer("✅ Tavsif yangilandi!" if ok else "❌ Tavsifni yangilab bo'lmadi.")
    else:
        await message.answer("O'tkazib yuborildi.")

    await state.clear()


# ------------------------------------------------------------------
# 📊 Tarif — tanlash va sotib olish (platforma balansidan yechiladi)
# ------------------------------------------------------------------

def tariff_menu(bot_id: int) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(
            text=f"{t.title} — {t.price_per_month:,} so'm/oy".replace(",", " "),
            callback_data=f"buytariff:{bot_id}:{t.key}",
        )]
        for t in TARIFFS.values()
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


@router.callback_query(F.data.startswith("bottariff:"))
async def show_tariffs(callback: CallbackQuery) -> None:
    bot_id = int(callback.data.split(":", 1)[1])
    await callback.message.answer(
        "📊 <b>Tariflar</b>\n\nHar bir tarif kunlik xabar/so'rov limitini belgilaydi:\n\n"
        + "\n".join(f"{t.title} — {t.daily_limit:,} so'rov/kun".replace(",", " ") for t in TARIFFS.values()),
        reply_markup=tariff_menu(bot_id),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("buytariff:"))
async def buy_tariff(callback: CallbackQuery) -> None:
    _, bot_id_str, tariff_key = callback.data.split(":")
    bot_id = int(bot_id_str)
    tariff = TARIFFS[tariff_key]

    async with get_session() as session:
        bot_result = await session.execute(select(Bot).where(Bot.id == bot_id))
        bot_row = bot_result.scalar_one()

        user_result = await session.execute(select(User).where(User.id == bot_row.owner_id))
        user = user_result.scalar_one()

        if tariff.price_per_month > 0 and user.balance < tariff.price_per_month:
            await callback.answer(
                f"⚠️ Balansda yetarli mablag' yo'q. Kerak: {tariff.price_per_month:,} so'm."
                .replace(",", " "),
                show_alert=True,
            )
            return

        if tariff.price_per_month > 0:
            user.balance -= tariff.price_per_month

        bot_row.tariff = tariff.key
        bot_row.expires_at = datetime.utcnow() + timedelta(days=30)
        await session.commit()

    await callback.message.answer(
        f"✅ <b>{tariff.title}</b> tarifiga o'tkazildi!\n"
        f"📅 Amal qilish muddati: 30 kun\n"
        f"⚡️ Kunlik limit: {tariff.daily_limit:,} so'rov".replace(",", " "),
    )
    await callback.answer("Tarif faollashtirildi ✅")


# ------------------------------------------------------------------
# 💰 To'lov (bot uchun) — joriy tarifni 30 kunga uzaytirish
# ------------------------------------------------------------------

@router.callback_query(F.data.startswith("bottopup:"))
async def extend_tariff(callback: CallbackQuery) -> None:
    bot_id = int(callback.data.split(":", 1)[1])

    async with get_session() as session:
        result = await session.execute(select(Bot).where(Bot.id == bot_id))
        bot_row = result.scalar_one()
        tariff = TARIFFS.get(bot_row.tariff, TARIFFS["free"])

    await callback.message.answer(
        f"💰 Joriy tarifingiz: <b>{tariff.title}</b> ({tariff.price_per_month:,} so'm/oy)\n\n"
        f"Muddatni 30 kunga uzaytirish uchun tarifni qayta tanlang:".replace(",", " "),
        reply_markup=tariff_menu(bot_id),
    )
    await callback.answer()


# ------------------------------------------------------------------
# ⚙️ Sozlash — bot turiga qarab (Taxi: haydovchilar guruhi, Anketa: savollar)
# ------------------------------------------------------------------

@router.callback_query(F.data.startswith("botsettings:"))
async def open_settings(callback: CallbackQuery, state: FSMContext) -> None:
    bot_id = int(callback.data.split(":", 1)[1])
    async with get_session() as session:
        result = await session.execute(select(Bot).where(Bot.id == bot_id))
        bot_row = result.scalar_one()

    await state.update_data(bot_id=bot_id)

    if bot_row.bot_type == "taxi":
        await state.set_state(SettingsStates.waiting_taxi_group)
        await callback.message.answer(
            "🚕 Haydovchilar guruhini sozlash:\n\n"
            "1. Bu botni guruhga admin qilib qo'shing\n"
            "2. Guruhda istalgan xabar yozing va shu xabarni shu yerga forward qiling\n\n"
            "Men guruh ID'sini avtomatik aniqlab olaman."
        )
    elif bot_row.bot_type == "anketa":
        await state.set_state(SettingsStates.waiting_anketa_questions)
        await callback.message.answer(
            "📝 Anketa savollarini yuboring — har bir savolni YANGI QATORDA yozing.\n\n"
            "Masalan:\nIsmingiz nima?\nYoshingiz nechida?\nQaysi shaharda yashaysiz?"
        )
    else:
        await callback.message.answer(
            "ℹ️ Bu bot turi uchun qo'shimcha sozlamalar hozircha yo'q — bot "
            "yaratilgan zahoti ishlashga tayyor."
        )

    await callback.answer()


@router.message(SettingsStates.waiting_taxi_group, F.forward_from_chat)
async def save_taxi_group(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    bot_id = data["bot_id"]
    group_id = message.forward_from_chat.id

    async with get_session() as session:
        result = await session.execute(select(Bot).where(Bot.id == bot_id))
        bot_row = result.scalar_one()
        settings = json.loads(bot_row.settings_json or "{}")
        settings["driver_group_id"] = group_id
        bot_row.settings_json = json.dumps(settings)
        await session.commit()

    await state.clear()
    await message.answer(f"✅ Haydovchilar guruhi sozlandi! (ID: {group_id})")


@router.message(SettingsStates.waiting_taxi_group)
async def taxi_group_wrong_input(message: Message) -> None:
    await message.answer("📎 Iltimos, guruhdagi xabarni shu yerga FORWARD qiling (oddiy matn emas).")


@router.message(SettingsStates.waiting_anketa_questions)
async def save_anketa_questions(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    bot_id = data["bot_id"]
    questions = [line.strip() for line in message.text.splitlines() if line.strip()]

    if not questions:
        await message.answer("❌ Kamida bitta savol kiriting.")
        return

    async with get_session() as session:
        result = await session.execute(select(Bot).where(Bot.id == bot_id))
        bot_row = result.scalar_one()
        settings = json.loads(bot_row.settings_json or "{}")
        settings["questions"] = questions
        bot_row.settings_json = json.dumps(settings)
        await session.commit()

    await state.clear()
    await message.answer(
        f"✅ {len(questions)} ta savol saqlandi!\n\n"
        + "\n".join(f"{i + 1}. {q}" for i, q in enumerate(questions))
    )
