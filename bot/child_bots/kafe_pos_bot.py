from database.db import get_session
from .base import ChildBot


class KafePosBot(ChildBot):
    """
    Kafe xodimlari uchun ichki tizim (mijoz uchun EMAS).
    Ofitsiant buyurtma yozadi -> oshxona guruhiga (kitchen_group_id) yuboriladi.
    settings: kitchen_group_id, staff_ids (ruxsat berilgan xodimlar ro'yxati)
    """

    async def handle_update(self, update: dict) -> None:
        message = update.get("message")
        if not message:
            return

        chat_id = message["chat"]["id"]
        text = (message.get("text") or "").strip()
        staff_ids = self.settings.get("staff_ids", [])
        is_owner = chat_id == self.settings.get("owner_telegram_id")

        if text == "/start":
            if is_owner:
                await self.send_message(
                    chat_id,
                    "🍽 Kafe POS boshqaruvi.\n\n"
                    "Xodim qo'shish: /add_staff <telegram_id>\n"
                    "Buyurtma qabul qilish uchun xodimlar shu botga stol raqami "
                    "va taomlarni yozib yuborishi kifoya.",
                )
            elif chat_id in staff_ids:
                await self.send_message(chat_id, "🍽 Xush kelibsiz! Buyurtmani yozing (masalan: Stol 5: 2x osh, 1x salat)")
            else:
                await self.send_message(chat_id, "⛔️ Sizga ruxsat berilmagan.")
            return

        if is_owner and text.startswith("/add_staff"):
            parts = text.split()
            if len(parts) == 2 and parts[1].isdigit():
                staff_ids.append(int(parts[1]))
                self.settings["staff_ids"] = staff_ids
                async with get_session() as session:
                    await self.save_settings(session)
                    await session.commit()
                await self.send_message(chat_id, f"✅ Xodim qo'shildi: {parts[1]}")
            return

        if chat_id in staff_ids and text:
            kitchen_group_id = self.settings.get("kitchen_group_id")
            if kitchen_group_id:
                await self.send_message(kitchen_group_id, f"🧾 <b>Yangi buyurtma:</b>\n{text}")
            await self.send_message(chat_id, "✅ Buyurtma oshxonaga yuborildi.")
