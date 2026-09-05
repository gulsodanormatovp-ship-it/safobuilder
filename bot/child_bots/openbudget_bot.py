from database.db import get_session
from .base import ChildBot


class OpenBudgetBot(ChildBot):
    """
    Ovoz yig'ish boti. Owner nomzodlar (loyihalar) ro'yxatini sozlaydi
    (Mini App yoki /addcandidate orqali), foydalanuvchilar bittasiga ovoz beradi.
    settings["candidates"] = ["Loyiha A", "Loyiha B", ...]
    settings["votes"] = {user_id: candidate_index}
    """

    async def handle_update(self, update: dict) -> None:
        message = update.get("message")
        callback = update.get("callback_query")
        candidates = self.settings.get("candidates", [])
        votes = self.settings.setdefault("votes", {})

        if callback:
            data = callback["data"]
            chat_id = callback["from"]["id"]
            if data.startswith("vote:"):
                idx = int(data.split(":", 1)[1])
                key = str(chat_id)
                if key in votes:
                    await self.answer_callback(callback["id"], "Siz allaqachon ovoz bergansiz.")
                    return
                votes[key] = idx
                await self._persist(votes)
                await self.answer_callback(callback["id"], "✅ Ovozingiz qabul qilindi!")
                await self.send_message(chat_id, f"Siz \"{candidates[idx]}\" uchun ovoz berdingiz. Rahmat!")
            return

        if not message:
            return

        chat_id = message["chat"]["id"]
        text = (message.get("text") or "").strip()

        if text == "/start":
            if not candidates:
                await self.send_message(chat_id, "⚠️ Ovoz berish hali sozlanmagan.")
                return
            buttons = [[{"text": c, "callback_data": f"vote:{i}"}] for i, c in enumerate(candidates)]
            await self.call_api(
                "sendMessage", chat_id=chat_id,
                text="📦 <b>Open Budget</b>\n\nQaysi loyihaga ovoz berasiz?",
                parse_mode="HTML",
                reply_markup={"inline_keyboard": buttons},
            )
            return

        if text == "/natija" and chat_id == self.settings.get("owner_telegram_id"):
            if not candidates:
                await self.send_message(chat_id, "Nomzodlar yo'q.")
                return
            counts = {i: 0 for i in range(len(candidates))}
            for v in votes.values():
                counts[v] = counts.get(v, 0) + 1
            lines = [f"{candidates[i]}: {counts.get(i, 0)} ovoz" for i in range(len(candidates))]
            await self.send_message(chat_id, "📊 <b>Natijalar</b>\n\n" + "\n".join(lines))

    async def _persist(self, votes: dict) -> None:
        self.settings["votes"] = votes
        async with get_session() as session:
            await self.save_settings(session)
            await session.commit()
