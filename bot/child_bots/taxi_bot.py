from database.db import get_session
from .base import ChildBot


class TaxiOrderStates:
    IDLE = "idle"
    WAITING_FROM = "waiting_from"
    WAITING_TO = "waiting_to"
    WAITING_PHONE = "waiting_phone"


class TaxiBot(ChildBot):
    """
    /start endi 3+ tugmali menyu bilan ochiladi: Buyurtma berish, Buyurtmalarim,
    Yordam. Buyurtma jarayonining o'zi (manzil, telefon) matn orqali davom etadi,
    chunki erkin matn kiritish talab qiladi.
    """

    def _main_menu(self) -> dict:
        return {"inline_keyboard": [
            [{"text": "🚕 Buyurtma berish", "callback_data": "taxi:order"}],
            [{"text": "📋 Buyurtmalarim", "callback_data": "taxi:my_orders"}],
            [{"text": "ℹ️ Yordam", "callback_data": "taxi:help"}],
        ]}

    async def handle_update(self, update: dict) -> None:
        message = update.get("message")
        callback = update.get("callback_query")
        sessions = self.settings.setdefault("sessions", {})

        if callback:
            chat_id = callback["from"]["id"]
            data = callback["data"]
            if data == "taxi:order":
                await self.answer_callback(callback["id"])
                await self._start_order(chat_id, sessions)
            elif data == "taxi:my_orders":
                history = self.settings.get("order_history", {}).get(str(chat_id), [])
                text = "\n\n".join(history[-5:]) if history else "Hali buyurtmalaringiz yo'q."
                await self.answer_callback(callback["id"])
                await self.send_message(chat_id, f"📋 <b>So'nggi buyurtmalar:</b>\n\n{text}")
            elif data == "taxi:help":
                await self.answer_callback(callback["id"])
                await self.send_message(chat_id, "ℹ️ \"Buyurtma berish\" tugmasini bosing va manzillarni kiriting.")
            return

        if not message:
            return

        chat_id = message["chat"]["id"]
        text = (message.get("text") or "").strip()
        state = sessions.get(str(chat_id), {}).get("state", TaxiOrderStates.IDLE)

        if text == "/start":
            await self.call_api(
                "sendMessage", chat_id=chat_id,
                text="🚕 <b>Taxi xizmatiga xush kelibsiz!</b>",
                parse_mode="HTML",
                reply_markup=self._main_menu(),
            )
            return

        if state == TaxiOrderStates.WAITING_FROM and text:
            sessions[str(chat_id)] = {"state": TaxiOrderStates.WAITING_TO, "from": text}
            await self._persist(sessions)
            await self.send_message(chat_id, "📍 Qayerga borasiz?")
            return

        if state == TaxiOrderStates.WAITING_TO and text:
            data = sessions[str(chat_id)]
            data["to"] = text
            data["state"] = TaxiOrderStates.WAITING_PHONE
            await self._persist(sessions)
            await self.send_message(chat_id, "📱 Telefon raqamingizni yuboring")
            return

        if state == TaxiOrderStates.WAITING_PHONE and text:
            data = sessions[str(chat_id)]
            await self._submit_order(chat_id, message, data["from"], data["to"], text)
            sessions[str(chat_id)] = {"state": TaxiOrderStates.IDLE}
            await self._persist(sessions)
            return

    async def _start_order(self, chat_id: int, sessions: dict) -> None:
        sessions[str(chat_id)] = {"state": TaxiOrderStates.WAITING_FROM}
        await self._persist(sessions)
        await self.send_message(chat_id, "📍 Qayerdan olib ketishimiz kerak?")

    async def _submit_order(self, chat_id: int, message: dict, place_from: str,
                             place_to: str, phone: str) -> None:
        await self.send_message(
            chat_id,
            f"✅ Buyurtmangiz qabul qilindi!\n\n📍 {place_from} → {place_to}\n📱 {phone}",
        )

        history = self.settings.setdefault("order_history", {})
        history.setdefault(str(chat_id), []).append(f"{place_from} → {place_to} ({phone})")

        driver_group_id = self.settings.get("driver_group_id")
        if driver_group_id:
            user = message["from"]
            name = user.get("first_name", "Mijoz")
            await self.send_message(
                driver_group_id,
                f"🚕 <b>Yangi buyurtma!</b>\n\n👤 {name}\n📍 {place_from} → {place_to}\n📱 {phone}",
            )

        async with get_session() as session:
            await self.save_settings(session)
            await session.commit()

    async def _persist(self, sessions: dict) -> None:
        self.settings["sessions"] = sessions
        async with get_session() as session:
            await self.save_settings(session)
            await session.commit()
