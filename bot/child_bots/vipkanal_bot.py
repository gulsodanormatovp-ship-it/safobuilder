from datetime import datetime, timedelta

from database.db import get_session
from .base import ChildBot


class VipKanalBot(ChildBot):
    """
    VIP kanal/guruhga pullik obuna sotish. Foydalanuvchi \"Obuna bo'lish\"
    tugmasini bosadi -> chek yuboradi -> owner tasdiqlaydi -> bot foydalanuvchiga
    bir martalik taklif havolasi (invite link) yuboradi.
    settings: channel_id, price, subscribers = {user_id: expires_at_iso}
    settings["pending"] = {payment_key: user_id}
    """

    async def handle_update(self, update: dict) -> None:
        message = update.get("message")
        callback = update.get("callback_query")

        if callback:
            chat_id = callback["from"]["id"]
            data = callback["data"]
            if data == "vip:subscribe":
                price = self.settings.get("price", 0)
                await self.answer_callback(callback["id"])
                await self.send_message(
                    chat_id,
                    f"💳 Obuna narxi: {price:,} so'm.\n\n"
                    f"To'lov qilgandan so'ng chek skrinshotini shu yerga yuboring.".replace(",", " "),
                )
            elif data.startswith("vip:approve:"):
                target_id = int(data.split(":")[2])
                await self._approve(target_id, callback)
            return

        if not message:
            return

        chat_id = message["chat"]["id"]
        is_owner = chat_id == self.settings.get("owner_telegram_id")
        text = (message.get("text") or "").strip()

        if text == "/start":
            price = self.settings.get("price", 0)
            await self.call_api(
                "sendMessage", chat_id=chat_id,
                text=f"🔐 <b>VIP kanalga xush kelibsiz!</b>\n\nObuna narxi: {price:,} so'm/oy".replace(",", " "),
                parse_mode="HTML",
                reply_markup={"inline_keyboard": [[{"text": "💳 Obuna bo'lish", "callback_data": "vip:subscribe"}]]},
            )
            return

        if "photo" in message and not is_owner:
            owner_id = self.settings.get("owner_telegram_id")
            if owner_id:
                await self.call_api(
                    "sendPhoto", chat_id=owner_id,
                    photo=message["photo"][-1]["file_id"],
                    caption=f"🧾 Yangi chek (user {chat_id})",
                    reply_markup={"inline_keyboard": [[
                        {"text": "✅ Tasdiqlash", "callback_data": f"vip:approve:{chat_id}"}
                    ]]},
                )
                await self.send_message(chat_id, "✅ Chekingiz admin ko'rib chiqishga yuborildi.")

    async def _approve(self, target_id: int, callback: dict) -> None:
        channel_id = self.settings.get("channel_id")
        if channel_id is None:
            await self.answer_callback(callback["id"], "⚠️ Kanal sozlanmagan.")
            return

        invite = await self.call_api("createChatInviteLink", chat_id=channel_id, member_limit=1)
        invite_link = invite.get("result", {}).get("invite_link")

        subscribers = self.settings.setdefault("subscribers", {})
        subscribers[str(target_id)] = (datetime.utcnow() + timedelta(days=30)).isoformat()
        async with get_session() as session:
            await self.save_settings(session)
            await session.commit()

        if invite_link:
            await self.send_message(
                target_id,
                f"✅ To'lovingiz tasdiqlandi!\n\n🔗 Kanalga qo'shilish havolasi:\n{invite_link}",
            )
        await self.answer_callback(callback["id"], "Tasdiqlandi ✅")
