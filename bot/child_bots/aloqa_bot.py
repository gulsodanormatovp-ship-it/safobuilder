from .base import ChildBot


class AloqaBot(ChildBot):
    """
    Foydalanuvchi -> bot -> owner (forward). Owner reply qilsa -> foydalanuvchiga qaytadi.
    settings["threads"] = {message_id_in_owner_chat: user_chat_id}  (reply orqali javob berish uchun)
    """

    async def handle_update(self, update: dict) -> None:
        message = update.get("message")
        if not message:
            return

        chat_id = message["chat"]["id"]
        owner_id = self.settings.get("owner_telegram_id")
        text = (message.get("text") or "").strip()

        if text == "/start":
            await self.send_message(
                chat_id,
                "📞 Xush kelibsiz! Murojaatingizni yozing — tez orada javob beramiz.",
            )
            return

        if chat_id == owner_id and message.get("reply_to_message"):
            # Owner forward qilingan xabarga reply qilyapti -> foydalanuvchiga yuboramiz
            threads = self.settings.get("threads", {})
            original_id = str(message["reply_to_message"]["message_id"])
            target_user = threads.get(original_id)
            if target_user and text:
                await self.send_message(target_user, f"💬 <b>Admin javobi:</b>\n{text}")
                await self.send_message(chat_id, "✅ Javob yuborildi.")
            return

        if chat_id != owner_id and owner_id:
            forwarded = await self.call_api(
                "forwardMessage", chat_id=owner_id,
                from_chat_id=chat_id, message_id=message["message_id"],
            )
            fwd_msg_id = forwarded.get("result", {}).get("message_id")
            if fwd_msg_id:
                threads = self.settings.setdefault("threads", {})
                threads[str(fwd_msg_id)] = chat_id
                from database.db import get_session
                async with get_session() as session:
                    await self.save_settings(session)
                    await session.commit()
            await self.send_message(chat_id, "✅ Murojaatingiz qabul qilindi, tez orada javob beramiz.")
