from database.db import get_session
from .base import ChildBot


class AnketaBot(ChildBot):
    """
    /start endi 3+ tugmali menyu bilan ochiladi: Boshlash, Natijalarim (owner),
    Yordam. Savol-javob jarayonining o'zi matn orqali davom etadi.
    """

    def _main_menu(self, is_owner: bool) -> dict:
        rows = [
            [{"text": "📝 Boshlash", "callback_data": "anketa:begin"}],
            [{"text": "ℹ️ Yordam", "callback_data": "anketa:help"}],
        ]
        if is_owner:
            rows.insert(1, [{"text": "📊 Barcha javoblar", "callback_data": "anketa:results"}])
        return {"inline_keyboard": rows}

    async def handle_update(self, update: dict) -> None:
        message = update.get("message")
        callback = update.get("callback_query")
        questions = self.settings.get("questions", [])
        responses = self.settings.setdefault("responses", {})

        if callback:
            chat_id = callback["from"]["id"]
            data = callback["data"]
            is_owner = chat_id == self.settings.get("owner_telegram_id")

            if data == "anketa:begin":
                await self.answer_callback(callback["id"])
                await self._begin(chat_id, questions, responses)
            elif data == "anketa:help":
                await self.answer_callback(callback["id"])
                await self.send_message(chat_id, "ℹ️ \"Boshlash\" tugmasini bosing va savollarga ketma-ket javob bering.")
            elif data == "anketa:results" and is_owner:
                await self.answer_callback(callback["id"])
                completed = sum(1 for r in responses.values() if r.get("index", 0) >= len(questions))
                await self.send_message(chat_id, f"📊 Jami to'ldirilgan anketalar: {completed} ta")
            return

        if not message:
            return

        chat_id = message["chat"]["id"]
        text = (message.get("text") or "").strip()
        is_owner = chat_id == self.settings.get("owner_telegram_id")
        key = str(chat_id)

        if text == "/start":
            await self.call_api(
                "sendMessage", chat_id=chat_id,
                text="📝 <b>Anketaga xush kelibsiz!</b>",
                parse_mode="HTML",
                reply_markup=self._main_menu(is_owner),
            )
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
                await self.send_message(owner_id, f"📩 <b>Yangi anketa javobi</b> (user {chat_id})\n\n{answers_text}")

    async def _begin(self, chat_id: int, questions: list, responses: dict) -> None:
        if not questions:
            await self.send_message(chat_id, "⚠️ Bu anketa hali sozlanmagan.")
            return
        responses[str(chat_id)] = {"index": 0, "answers": []}
        await self._persist(responses)
        await self.send_message(chat_id, f"📝 Anketa boshlandi!\n\n1) {questions[0]}")

    async def _persist(self, responses: dict) -> None:
        self.settings["responses"] = responses
        async with get_session() as session:
            await self.save_settings(session)
            await session.commit()
