from database.db import get_session
from .base import ChildBot


class TaxiOrderStates:
    IDLE = "idle"
    WAITING_FROM = "waiting_from"
    WAITING_TO = "waiting_to"
    WAITING_PHONE = "waiting_phone"


class TaxiBot(ChildBot):
    """
    Foydalanuvchi: manzil (qayerdan/qayerga) va telefon raqamini kiritadi ->
    buyurtma haydovchilar guruhiga (settings['driver_group_id']) yuboriladi.
    Har bir foydalanuvchining joriy holati settings['sessions'][user_id] da saqlanadi
    (production'da bu alohida jadvalda bo'lishi kerak — bu yerda soddalik uchun shu yerda).
    """

    async def handle_update(self, update: dict) -> None:
        message = update.get("message")
        if not message:
            return

        chat_id = message["chat"]["id"]
        text = (message.get("text") or "").strip()
        sessions = self.settings.setdefault("sessions", {})
        state = sessions.get(str(chat_id), {}).get("state", TaxiOrderStates.IDLE)

        if text == "/start":
            await self._start_order(chat_id, sessions)
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
            await self.send_message(chat_id, "📱 Telefon raqamingizni yuboring (masalan +998901234567)")
            return

        if state == TaxiOrderStates.WAITING_PHONE and text:
            data = sessions[str(chat_id)]
            await self._submit_order(chat_id, message, data["from"], data["to"], text)
            sessions[str(chat_id)] = {"state": TaxiOrderStates.IDLE}
            await self._persist(sessions)
            return

        if text != "/start":
            await self.send_message(chat_id, "🚕 Buyurtma berish uchun /start bosing.")

    async def _start_order(self, chat_id: int, sessions: dict) -> None:
        sessions[str(chat_id)] = {"state": TaxiOrderStates.WAITING_FROM}
        await self._persist(sessions)
        await self.send_message(chat_id, "🚕 Taxi buyurtma\n\n📍 Qayerdan olib ketishimiz kerak?")

    async def _submit_order(self, chat_id: int, message: dict, place_from: str,
                             place_to: str, phone: str) -> None:
        await self.send_message(
            chat_id,
            f"✅ Buyurtmangiz qabul qilindi!\n\n"
            f"📍 {place_from} → {place_to}\n📱 {phone}\n\n"
            f"Tez orada haydovchi siz bilan bog'lanadi.",
        )

        driver_group_id = self.settings.get("driver_group_id")
        if driver_group_id:
            user = message["from"]
            name = user.get("first_name", "Mijoz")
            await self.send_message(
                driver_group_id,
                f"🚕 <b>Yangi buyurtma!</b>\n\n"
                f"👤 {name}\n📍 {place_from} → {place_to}\n📱 {phone}",
            )

    async def _persist(self, sessions: dict) -> None:
        self.settings["sessions"] = sessions
        async with get_session() as session:
            await self.save_settings(session)
            await session.commit()
