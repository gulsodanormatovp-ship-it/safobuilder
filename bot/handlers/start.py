from aiogram import F, Router
from aiogram.filters import CommandObject, CommandStart
from aiogram.types import Message
from sqlalchemy import select

from bot.keyboards import MAIN_MENU
from database.db import get_session
from database.models import Referral, User

router = Router(name="start")

WELCOME_TEXT = (
    "🛡 <b>Vezto — Telegram botlar yaratish uchun qulay platforma</b>\n\n"
    "Bu platforma orqali siz hech qanday kod yozmasdan o'z Telegram "
    "botlaringizni tez va oson yaratishingiz, ularni tahrirlashingiz hamda "
    "boshqarishingiz mumkin.\n\n"
    "⚡️ <b>Nega aynan Vezto?</b>\n"
    "• Botlar muntazam yangilanib boriladi\n"
    "• Barqaror va mukammal ishlaydigan tizim\n"
    "• To'liq o'zbek tilidagi qulay interfeys\n"
    "• Doimiy va tezkor qo'llab-quvvatlash xizmati\n"
    "• Barcha jarayonlar avtomatik va tushunarli\n"
    "• Mini App orqali to'liq boshqaruv va statistika"
)


@router.message(CommandStart())
async def cmd_start(message: Message, command: CommandObject) -> None:
    async with get_session() as session:
        result = await session.execute(
            select(User).where(User.telegram_id == message.from_user.id)
        )
        user = result.scalar_one_or_none()

        if user is None:
            # Middleware odatda buni allaqachon yaratgan bo'ladi, lekin
            # ehtiyot chorasi sifatida shu yerda ham tekshiramiz.
            user = User(
                telegram_id=message.from_user.id,
                username=message.from_user.username,
                full_name=message.from_user.full_name,
            )
            session.add(user)
            await session.flush()

        # Referal bog'lanishi hali qilinmagan bo'lsa va havolada referrer
        # ko'rsatilgan bo'lsa — bog'laymiz va bonus beramiz. `is_new`ga
        # emas, `referred_by`ning bo'shligiga qaraymiz, chunki foydalanuvchi
        # bu nuqtaga kelguncha middleware orqali allaqachon yaratilgan bo'lishi mumkin.
        if user.referred_by is None and command.args and command.args.isdigit():
            ref_result = await session.execute(
                select(User).where(User.telegram_id == int(command.args))
            )
            referrer = ref_result.scalar_one_or_none()
            if referrer and referrer.id != user.id:
                user.referred_by = referrer.id
                session.add(Referral(referrer_id=referrer.id, referred_id=user.id))
                referrer.balance += 500  # bonus — .env orqali sozlanadi

        await session.commit()

    await message.answer(WELCOME_TEXT, reply_markup=MAIN_MENU)


@router.message(F.text == "📚 Qo'llanma")
async def show_guide(message: Message) -> None:
    await message.answer(
        "📚 <b>Botdan foydalanish qo'llanmalari:</b>\n\n"
        "📖 Bot yaratish bo'yicha to'liq qo'llanma pastdagi havolada."
    )
