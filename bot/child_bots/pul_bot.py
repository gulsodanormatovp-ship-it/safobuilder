from database.db import get_session
from .base import ChildBot


class PulBot(ChildBot):
    """
    Referal orqali pul ishlash boti. Har bir foydalanuvchi o'z havolasini
    tarqatadi, yangi odam qo'shilganda unga bonus tushadi.
    settings["users"] = {user_id: {"balance": int, "invited": int}}
    settings["bonus_per_invite"] = 1000  (owner belgilaydi, default 1000)
    """

    async def handle_update(self, update: dict) -> None:
        message = update.get("message")
        if not message:
            return

        chat_id = message["chat"]["id"]
        text = (message.get("text") or "").strip()
        users = self.settings.setdefault("users", {})
        bonus = self.settings.get("bonus_per_invite", 1000)
        key = str(chat_id)

        if key not in users:
            users[key] = {"balance": 0, "invited": 0}

        if text.startswith("/start"):
            parts = text.split()
            referrer_id = parts[1] if len(parts) > 1 and parts[1].isdigit() else None

            if referrer_id and referrer_id != key and referrer_id in users \
                    and not users[key].get("came_from"):
                users[key]["came_from"] = referrer_id
                users[referrer_id]["balance"] += bonus
                users[referrer_id]["invited"] += 1
                await self._persist(users)
                await self.send_message(
                    int(referrer_id),
                    f"🎉 Sizning havolangiz orqali yangi foydalanuvchi qo'shildi! "
                    f"+{bonus:,} so'm balansingizga tushdi.".replace(",", " "),
                )

            bot_username = self.bot_row.bot_username
            link = f"https://t.me/{bot_username}?start={chat_id}"
            await self._persist(users)
            await self.send_message(
                chat_id,
                f"💰 Xush kelibsiz!\n\nHar bir taklif qilingan do'stingiz uchun "
                f"{bonus:,} so'm olasiz.\n\n"
                f"👛 Balansingiz: {users[key]['balance']:,} so'm\n"
                f"👥 Takliflaringiz: {users[key]['invited']} ta\n\n"
                f"🔗 Havolangiz:\n{link}".replace(",", " "),
            )
            return

        if text == "/balance":
            await self.send_message(
                chat_id,
                f"👛 Balansingiz: {users[key]['balance']:,} so'm\n"
                f"👥 Takliflaringiz: {users[key]['invited']} ta".replace(",", " "),
            )

    async def _persist(self, users: dict) -> None:
        self.settings["users"] = users
        async with get_session() as session:
            await self.save_settings(session)
            await session.commit()
