from database.db import get_session
from .base import ChildBot


class AnketaBot(ChildBot):
    """
    settings["questions"] = ["Ismingiz?", "Yoshingiz?", ...]  (owner sozlaydi, Mini App orqali)
    settings["responses"] = {user_id: {"index": 0, "answers": [...]}}
    Barcha savollarga javob berilgach, natija owner'ga yuboriladi va
    Mini App orqali CSV holida eksport qilinishi mumkin (api/main.py dagi
    /api/bots/{id}/anketa-export endpointi).
    """

    async def handle_update(self, update: dict) -> None:
        message = update.get("message")
        if not message:
            return

        chat_id = message["chat"]["id"]
        text = (message.get("text") or "").strip()
        questions = self.settings.get("questions", [])
        responses = self.settings.setdefault("responses", {})
        key = str(chat_id)

        if text == "/start":
            if not questions:
                await self.send_message(chat_id, "⚠️ Bu anketa hali sozlanmagan.")
                return
            responses[key] = {"index": 0, "answers": []}
            await self._persist(responses)
            await self.send_message(chat_id, f"📝 Anketa boshlandi!\n\n1) {questions[0]}")
            return

        session_data = responses.get(key)
        if session_data is None or not text:
            return

        session_data["answers"].append(text)
        session_data["index"] += 1
        idx = session_data["index"]

        if idx < len(questions):
            await self._persist(responses)
            await self.send_message(chat_id, f"{idx + 1}) {questions[idx]}")
        else:
            await self._persist(responses)
            await self.send_message(chat_id, "✅ Anketa yakunlandi! Javoblaringiz uchun rahmat.")
            owner_id = self.settings.get("owner_telegram_id")
            if owner_id:
                answers_text = "\n".join(
                    f"{i + 1}. {q}\n➡️ {a}" for i, (q, a) in
                    enumerate(zip(questions, session_data["answers"]))
                )
                await self.send_message(
                    owner_id,
                    f"📩 <b>Yangi anketa javobi</b> (user {chat_id})\n\n{answers_text}",
                )

    async def _persist(self, responses: dict) -> None:
        self.settings["responses"] = responses
        async with get_session() as session:
            await self.save_settings(session)
            await session.commit()
