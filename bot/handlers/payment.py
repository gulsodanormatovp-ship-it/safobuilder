import os

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message
from sqlalchemy import select

from bot.keyboards import MAIN_MENU, admin_payment_review, payment_methods_menu
from database.db import get_session
from database.models import Payment, PaymentMethod, PaymentStatus, User

router = Router(name="payment")

ADMIN_CHAT_ID = int(os.getenv("ADMIN_CHAT_ID", "0"))
CARD_NUMBER = os.getenv("PAYMENT_CARD_NUMBER", "8600 0000 0000 0000")
CARD_OWNER = os.getenv("PAYMENT_CARD_OWNER", "SAFOBUILDER")


class TopUpStates(StatesGroup):
    waiting_amount = State()
    waiting_receipt = State()


@router.message(F.text == "💳 Hisob to'ldirish")
async def topup_entry(message: Message, state: FSMContext) -> None:
    await state.set_state(TopUpStates.waiting_amount)
    await message.answer(
        "💳 To'ldirmoqchi bo'lgan summani kiriting (so'mda). Masalan: <code>50000</code>"
    )


@router.message(TopUpStates.waiting_amount)
async def topup_amount(message: Message, state: FSMContext) -> None:
    text = (message.text or "").replace(" ", "")
    if not text.isdigit() or not (1000 <= int(text) <= 50_000_000):
        await message.answer("❌ 1 000 dan 50 000 000 so'mgacha son kiriting.")
        return
    await state.update_data(amount=int(text))
    await message.answer(
        "To'lov usulini tanlang:\n\n"
        "🔵 <b>Click / Payme / Paynet</b> — avtomatik, mablag' darhol tushadi.\n"
        "💵 <b>Naqd pul orqali (Paynet bankomat)</b> — bankomatga naqd solasiz, "
        "mablag' avtomatik tushadi.\n"
        "💳 <b>Karta orqali</b> — kartaga o'tkazasiz va chekni yuborasiz, "
        "<b>admin tasdiqlagandan keyin</b> mablag'ingiz tushadi.",
        reply_markup=payment_methods_menu(),
    )


@router.callback_query(F.data.in_({"pay:click", "pay:payme", "pay:paynet", "pay:paynet_cash"}))
async def automatic_payment_stub(callback: CallbackQuery, state: FSMContext) -> None:
    """
    Bu usullar haqiqiy integratsiyada Click/Payme/Paynet merchant API'siga
    ulanadi (invoice yaratish -> to'lov linki -> webhook orqali tasdiqlash).
    Bu yerda joy egallovchi (placeholder) — haqiqiy merchant hisobingiz
    bo'lgach shu funksiyani to'ldirasiz.
    """
    await callback.answer(
        "Bu to'lov usuli hozircha ulanmagan. Iltimos, \"Karta orqali\" ni tanlang.",
        show_alert=True,
    )


@router.callback_query(F.data == "pay:card_manual")
async def card_manual_start(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(TopUpStates.waiting_receipt)
    await callback.message.answer(
        f"💳 Quyidagi kartaga to'lov qiling:\n\n"
        f"<code>{CARD_NUMBER}</code>\n"
        f"👤 {CARD_OWNER}\n\n"
        f"To'lov qilgandan so'ng <b>chek skrinshotini</b> shu yerga rasm qilib yuboring.\n"
        f"Admin tasdiqlagach mablag'ingiz avtomatik hisobingizga tushadi ⏳"
    )
    await callback.answer()


@router.message(TopUpStates.waiting_receipt, F.photo)
async def receive_receipt(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    amount = data["amount"]
    receipt_file_id = message.photo[-1].file_id

    async with get_session() as session:
        result = await session.execute(
            select(User).where(User.telegram_id == message.from_user.id)
        )
        user = result.scalar_one()

        payment = Payment(
            user_id=user.id,
            amount=amount,
            method=PaymentMethod.CARD_MANUAL,
            status=PaymentStatus.PENDING,
            receipt_file_id=receipt_file_id,
        )
        session.add(payment)
        await session.flush()
        payment_id = payment.id
        await session.commit()

    await state.clear()
    await message.answer(
        "✅ Chekingiz qabul qilindi va admin ko'rib chiqishga yuborildi.\n"
        "Odatda 5-30 daqiqa ichida tasdiqlanadi.",
        reply_markup=MAIN_MENU,
    )

    if ADMIN_CHAT_ID:
        await message.bot.send_photo(
            chat_id=ADMIN_CHAT_ID,
            photo=receipt_file_id,
            caption=(
                f"🧾 <b>Yangi to'lov cheki</b>\n\n"
                f"👤 Foydalanuvchi: {message.from_user.full_name} "
                f"(@{message.from_user.username or '—'}, id: {message.from_user.id})\n"
                f"💵 Summa: {amount:,} so'm\n"
                f"🆔 Payment ID: {payment_id}".replace(",", " ")
            ),
            reply_markup=admin_payment_review(payment_id),
        )


@router.message(TopUpStates.waiting_receipt)
async def receipt_wrong_type(message: Message) -> None:
    await message.answer("📷 Iltimos, chekning rasmini (screenshot) yuboring.")


# ---------------- Admin tasdiqlash oqimi ----------------

@router.callback_query(F.data.startswith("admin_approve:"))
async def admin_approve_payment(callback: CallbackQuery) -> None:
    payment_id = int(callback.data.split(":", 1)[1])

    async with get_session() as session:
        result = await session.execute(select(Payment).where(Payment.id == payment_id))
        payment = result.scalar_one_or_none()
        if payment is None or payment.status != PaymentStatus.PENDING:
            await callback.answer("Bu to'lov allaqachon ko'rib chiqilgan.", show_alert=True)
            return

        user_result = await session.execute(select(User).where(User.id == payment.user_id))
        user = user_result.scalar_one()

        user.balance += payment.amount
        payment.status = PaymentStatus.APPROVED
        payment.reviewed_by = callback.from_user.id
        await session.commit()
        target_telegram_id = user.telegram_id
        amount = payment.amount

    await callback.message.edit_caption(
        caption=callback.message.caption + "\n\n✅ <b>TASDIQLANDI</b>",
        reply_markup=None,
    )
    await callback.bot.send_message(
        chat_id=target_telegram_id,
        text=f"✅ To'lovingiz tasdiqlandi! Hisobingizga {amount:,} so'm qo'shildi.".replace(",", " "),
    )
    await callback.answer("Tasdiqlandi ✅")


@router.callback_query(F.data.startswith("admin_reject:"))
async def admin_reject_payment(callback: CallbackQuery) -> None:
    payment_id = int(callback.data.split(":", 1)[1])

    async with get_session() as session:
        result = await session.execute(select(Payment).where(Payment.id == payment_id))
        payment = result.scalar_one_or_none()
        if payment is None or payment.status != PaymentStatus.PENDING:
            await callback.answer("Bu to'lov allaqachon ko'rib chiqilgan.", show_alert=True)
            return

        payment.status = PaymentStatus.REJECTED
        payment.reviewed_by = callback.from_user.id

        user_result = await session.execute(select(User).where(User.id == payment.user_id))
        user = user_result.scalar_one()
        target_telegram_id = user.telegram_id
        await session.commit()

    await callback.message.edit_caption(
        caption=callback.message.caption + "\n\n❌ <b>RAD ETILDI</b>",
        reply_markup=None,
    )
    await callback.bot.send_message(
        chat_id=target_telegram_id,
        text="❌ To'lov chekingiz rad etildi. Sabab uchun \"Murojaat\" bo'limiga yozing.",
    )
    await callback.answer("Rad etildi ❌")
