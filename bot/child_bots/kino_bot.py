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
    Kodlar `settings["movies"] = {"123456": {"chat_id": .., "message_id": ..}}`
    ko'rinishida saqlanadi.
    """

    async def handle_update(self, update: dict) -> None:
        message = update.get("message")
        if not message:
            return

        chat_id = message["chat"]["id"]
        is_owner = chat_id == self.settings.get("owner_telegram_id")

        if "video" in message and is_owner:
            await self._save_movie(message, chat_id)
            return

        text = (message.get("text") or "").strip()
        if text == "/start":
            await self.send_message(
                chat_id,
                "🎬 Xush kelibsiz! Kino kodini yuboring va filmni oling.\n\n"
                + ("(Siz botning egasisiz — video yuborsangiz avtomatik kod olasiz)"
                   if is_owner else ""),
            )
            return

        if text.isdigit() and text in self.settings.get("movies", {}):
            movie = self.settings["movies"][text]
            await self.call_api(
                "copyMessage",
                chat_id=chat_id,
                from_chat_id=movie["chat_id"],
                message_id=movie["message_id"],
            )
            return

        if text.isdigit():
            await self.send_message(chat_id, "❌ Bunday kodli kino topilmadi.")
            return

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
            f"✅ Film saqlandi!\n🔑 Kod: <code>{code}</code>\n\n"
            f"Foydalanuvchilar shu kodni botga yuborib filmni olishlari mumkin.",
        )
