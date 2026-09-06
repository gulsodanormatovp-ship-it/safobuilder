import random
import string

from database.db import get_session
from .base import ChildBot


def _generate_code(length: int = 6) -> str:
    return "".join(random.choices(string.digits, k=length))


class KinoBot(ChildBot):
    """
    Owner (bot egasi) botga video yuboradi -> bot random kod beradi.
    Har qanday foydalanuvchi shu kodni yuborsa -> video qaytariladi.
    /start endi 3+ tugmali menyu bilan ochiladi.
    """

    def _main_menu(self, is_owner: bool) -> dict:
        rows = [
            [{"text": "🔎 Kino qidirish", "callback_data": "kino:search"}],
            [{"text": "🆕 Yangi kinolar", "callback_data": "kino:latest"}],
            [{"text": "ℹ️ Yordam", "callback_data": "kino:help"}],
        ]
        if is_owner:
            rows.append([{"text": "📊 Statistikam", "callback_data": "kino:stats"}])
        return {"inline_keyboard": rows}

    async def handle_update(self, update: dict) -> None:
        message = update.get("message")
        callback = update.get("callback_query")

        if callback:
            chat_id = callback["from"]["id"]
            data = callback["data"]
            is_owner = chat_id == self.settings.get("owner_telegram_id")

            if data == "kino:search":
                await self.answer_callback(callback["id"])
                await self.send_message(chat_id, "🔎 Kino kodini yuboring (masalan: 482913)")
            elif data == "kino:latest":
                movies = self.settings.get("movies", {})
                last_codes = list(movies.keys())[-5:]
                text = ("🆕 Oxirgi qo'shilgan kodlar:\n\n" + "\n".join(f"🔑 {c}" for c in last_codes)) \
                    if last_codes else "Hozircha kino yo'q."
                await self.answer_callback(callback["id"])
                await self.send_message(chat_id, text)
            elif data == "kino:help":
                await self.answer_callback(callback["id"])
                await self.send_message(chat_id, "ℹ️ Kino kodini yuboring — bot filmni avtomatik topib beradi.")
            elif data == "kino:stats" and is_owner:
                movies = self.settings.get("movies", {})
                await self.answer_callback(callback["id"])
                await self.send_message(chat_id, f"📊 Jami yuklangan kinolar: {len(movies)} ta")
            return

        if not message:
            return

        chat_id = message["chat"]["id"]
        is_owner = chat_id == self.settings.get("owner_telegram_id")

        if "video" in message and is_owner:
            await self._save_movie(message, chat_id)
            return

        text = (message.get("text") or "").strip()
        if text == "/start":
            await self.call_api(
                "sendMessage", chat_id=chat_id,
                text="🎬 <b>Xush kelibsiz!</b>\n\nKino kodini yuboring yoki quyidagi tugmalardan foydalaning:",
                parse_mode="HTML",
                reply_markup=self._main_menu(is_owner),
            )
            return

        if text.isdigit() and text in self.settings.get("movies", {}):
            movie = self.settings["movies"][text]
            await self.call_api(
                "copyMessage", chat_id=chat_id,
                from_chat_id=movie["chat_id"], message_id=movie["message_id"],
            )
            return

        if text.isdigit():
            await self.send_message(chat_id, "❌ Bunday kodli kino topilmadi.")

    async def _save_movie(self, message: dict, owner_chat_id: int) -> None:
        code = _generate_code()
        self.settings.setdefault("movies", {})[code] = {
            "chat_id": owner_chat_id,
            "message_id": message["message_id"],
        }
        async with get_session() as session:
            await self.save_settings(session)
            await session.commit()

        await self.send_message(
            owner_chat_id,
            f"✅ Film saqlandi!\n🔑 Kod: <code>{code}</code>",
        )
