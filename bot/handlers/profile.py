from aiogram import F, Router
from aiogram.types import Message
from sqlalchemy import func, select

from bot.keyboards import PUBLIC_BASE_URL, WEBAPP_BASE_URL
from database.db import get_session
from database.models import Bot, BotStatus, Referral, User

router = Router(name="profile")


@router.message(F.text == "🗣 Referal")
async def show_referral(message: Message) -> None:
    bot_username = (await message.bot.get_me()).username
    link = f"https://t.me/{bot_username}?start={message.from_user.id}"

    async with get_session() as session:
        result = await session.execute(
            select(User).where(User.telegram_id == message.from_user.id)
        )
        user = result.scalar_one()
        count_result = await session.execute(
            select(func.count()).select_from(Referral).where(Referral.referrer_id == user.id)
        )
        ref_count = count_result.scalar_one()

    await message.answer(
        "🎁 Do'stlaringizni taklif qiling va bonus oling!\n\n"
        f"Har bir taklif qilingan do'stingiz uchun <b>500 so'm</b> taqdim etiladi.\n\n"
        f"👥 Takliflaringiz: {ref_count} ta\n"
        f"👇 Boshlash uchun havolangiz:\n{link}"
    )


@router.message(F.text == "📱 Shaxsiy kabinet")
async def show_profile(message: Message) -> None:
    async with get_session() as session:
        result = await session.execute(
            select(User).where(User.telegram_id == message.from_user.id)
        )
        user = result.scalar_one()

        ref_count_result = await session.execute(
            select(func.count()).select_from(Referral).where(Referral.referrer_id == user.id)
        )
        ref_count = ref_count_result.scalar_one()

        bots_count_result = await session.execute(
            select(func.count()).select_from(Bot).where(
                Bot.owner_id == user.id, Bot.status != BotStatus.DELETED
            )
        )
        bots_count = bots_count_result.scalar_one()

    await message.answer(
        f"🆔 ID: {user.telegram_id}\n"
        f"├ 💼 Balansingiz: {user.balance:,} so'm\n".replace(",", " ")
        + f"├ 👥 Referallaringiz: {ref_count} ta\n"
        + f"├ 🤖 Botlaringiz: {bots_count} ta\n"
        + f"└ 💰 Kiritgan pullaringiz: 0 so'm"
    )


@router.message(F.text == "🌐 Saytga kirish")
async def open_website(message: Message) -> None:
    from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🚀 Tez kirish (Telegram ichida)",
                               web_app={"url": f"{WEBAPP_BASE_URL}?mode=dashboard"})],
        [InlineKeyboardButton(text="🌐 Brauzerda ochish", url=WEBAPP_BASE_URL)],
    ])
    await message.answer(
        "🌐 <b>Saytga kirish</b>\n\nQuyidagi tugmalardan birini tanlang:",
        reply_markup=kb,
    )


@router.message(F.text == "📩 Murojaat")
async def show_help_center(message: Message) -> None:
    from bot.keyboards import help_center_menu

    await message.answer("📩 <b>Yordam markazi</b>\n\nQuyidagilardan birini tanlang:",
                          reply_markup=help_center_menu())
