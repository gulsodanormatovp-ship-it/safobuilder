from aiogram import F, Router
from aiogram.types import CallbackQuery, Message
from sqlalchemy import select

from bot.bot_catalog import BOT_CATALOG
from bot.keyboards import bot_manage_menu, my_bots_menu
from database.db import get_session
from database.models import Bot, BotStatus, User

router = Router(name="my_bots")

STATUS_EMOJI = {BotStatus.ACTIVE: "🟢", BotStatus.PAUSED: "🟡", BotStatus.DELETED: "🔴"}


async def _get_user_bots(telegram_id: int) -> list[Bot]:
    async with get_session() as session:
        result = await session.execute(
            select(Bot).join(User).where(
                User.telegram_id == telegram_id, Bot.status != BotStatus.DELETED
            )
        )
        return list(result.scalars().all())


@router.message(F.text == "🤖 Botlarim")
async def list_my_bots(message: Message) -> None:
    bots = await _get_user_bots(message.from_user.id)
    active_count = sum(1 for b in bots if b.status == BotStatus.ACTIVE)

    if not bots:
        await message.answer(
            "🤖 Sizda hali botlar yo'q.\n\"➕ Bot yaratish\" bo'limidan birinchi botingizni yarating!"
        )
        return

    menu_data = [(b.id, b.bot_username, STATUS_EMOJI[b.status]) for b in bots]
    await message.answer(
        f"🤖 <b>Mening botlarim</b>\n\n🟢 Ishlayapti: {active_count}\n👇 Boshqarish uchun tanlang.",
        reply_markup=my_bots_menu(menu_data),
    )


@router.callback_query(F.data.startswith("managebot:"))
async def manage_bot(callback: CallbackQuery) -> None:
    bot_id = int(callback.data.split(":", 1)[1])
    async with get_session() as session:
        result = await session.execute(select(Bot).where(Bot.id == bot_id))
        bot_row = result.scalar_one_or_none()

    if bot_row is None:
        await callback.answer("Bot topilmadi.", show_alert=True)
        return

    info = BOT_CATALOG[bot_row.bot_type]
    await callback.message.edit_text(
        f"{info.emoji} <b>{bot_row.display_name}</b>\n"
        f"📎 @{bot_row.bot_username}\n"
        f"🏷 Tarif: {bot_row.tariff.title()}\n"
        f"📌 Holat: {bot_row.status.value}",
        reply_markup=bot_manage_menu(bot_id),
    )
    await callback.answer()


@router.callback_query(F.data == "my_bots")
async def back_to_my_bots(callback: CallbackQuery) -> None:
    bots = await _get_user_bots(callback.from_user.id)
    menu_data = [(b.id, b.bot_username, STATUS_EMOJI[b.status]) for b in bots]
    await callback.message.edit_text(
        "🤖 <b>Mening botlarim</b>\n\n👇 Boshqarish uchun tanlang.",
        reply_markup=my_bots_menu(menu_data),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("botdelete:"))
async def delete_bot(callback: CallbackQuery) -> None:
    bot_id = int(callback.data.split(":", 1)[1])
    async with get_session() as session:
        result = await session.execute(select(Bot).where(Bot.id == bot_id))
        bot_row = result.scalar_one()
        bot_row.status = BotStatus.DELETED
        await session.commit()

    await callback.message.edit_text("🗑 Bot o'chirildi.")
    await callback.answer()
