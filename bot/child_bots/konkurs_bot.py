from database.db import get_session
from .base import ChildBot


class KonkursBot(ChildBot):
    """
    Referal asosidagi konkurs. Ishtirokchilar o'z havolasini tarqatadi,
    eng ko'p taklif qilgan g'olib bo'ladi.
    settings["participants"] = {user_id: {"invited": int}}
    settings["prize_text"] = "1-o'rin: 500 000 so'm, ..."
    """

    async def handle_update(self, update: dict) -> None:
        message = update.get("message")
        if not message:
            return

        chat_id = message["chat"]["id"]
        text = (message.get("text") or "").strip()
        participants = self.settings.setdefault("participants", {})
        key = str(chat_id)

        if key not in participants:
            participants[key] = {"invited": 0}

        if text.startswith("/start"):
            parts = text.split()
            referrer_id = parts[1] if len(parts) > 1 and parts[1].isdigit() else None

            if referrer_id and referrer_id != key and referrer_id in participants \
                    and not participants[key].get("came_from"):
                participants[key]["came_from"] = referrer_id
                participants[referrer_id]["invited"] += 1
                await self._persist(participants)
                await self.send_message(
                    int(referrer_id),
                    f"🎉 Yana bir do'stingiz konkursga qo'shildi! "
                    f"Jami: {participants[referrer_id]['invited']} ta taklif.",
                )

            prize_text = self.settings.get("prize_text", "Sovrinlar tez orada e'lon qilinadi.")
            bot_username = self.bot_row.bot_username
            link = f"https://t.me/{bot_username}?start={chat_id}"
            await self._persist(participants)
            await self.send_message(
                chat_id,
                f"🏆 <b>Konkursga xush kelibsiz!</b>\n\n"
                f"🎁 Sovrinlar: {prize_text}\n\n"
                f"👥 Sizning takliflaringiz: {participants[key]['invited']} ta\n\n"
                f"🔗 Do'stlaringizni shu havola orqali taklif qiling:\n{link}",
            )
            return

        if text == "/top":
            top = sorted(participants.items(), key=lambda x: x[1]["invited"], reverse=True)[:10]
            lines = [f"{i + 1}. {uid} — {data['invited']} ta" for i, (uid, data) in enumerate(top)]
            await self.send_message(chat_id, "🏆 <b>TOP-10</b>\n\n" + "\n".join(lines) if lines else "Hali ishtirokchilar yo'q.")

    async def _persist(self, participants: dict) -> None:
        self.settings["participants"] = participants
        async with get_session() as session:
            await self.save_settings(session)
            await session.commit()
