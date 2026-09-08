from database.db import get_session
from .base import ChildBot


def _parse_questions(raw_lines: list[str]) -> list[dict]:
    """
    Har bir qator formati: Savol matni|Variant1|Variant2|Variant3|To'g'ri raqami
    Masalan: "2+2 nechi?|3|4|5|2"  (2-variant to'g'ri, ya'ni "4")
    """
    questions = []
    for line in raw_lines:
        parts = [p.strip() for p in line.split("|")]
        if len(parts) < 3:
            continue
        question_text = parts[0]
        *options, correct_str = parts[1:]
        if not correct_str.isdigit():
            continue
        correct_index = int(correct_str) - 1
        if 0 <= correct_index < len(options):
            questions.append({"question": question_text, "options": options, "correct_index": correct_index})
    return questions


class ViktorinaBot(ChildBot):
    """
    Bolalar va kattalar uchun qiziqarli viktorina/o'yin boti.
    Savollar owner tomonidan Mini App > Sozlash orqali quyidagi formatda kiritiladi:
        Savol matni|Variant1|Variant2|Variant3|To'g'ri_variant_raqami
    Har bir foydalanuvchi ketma-ket savollarga javob beradi, ball to'playdi,
    /top orqali reytingni ko'radi.
    settings["quiz_questions"] = ["savol|a|b|c|1", ...]
    settings["progress"] = {user_id: {"index": int, "score": int}}
    settings["leaderboard"] = {user_id: best_score}
    """

    def _questions(self) -> list[dict]:
        return _parse_questions(self.settings.get("quiz_questions", []))

    def _main_menu(self) -> dict:
        return {"inline_keyboard": [
            [{"text": "🎮 O'yinni boshlash", "callback_data": "quiz:start"}],
            [{"text": "🏆 Reyting (TOP-10)", "callback_data": "quiz:top"}],
            [{"text": "ℹ️ Yordam", "callback_data": "quiz:help"}],
        ]}

    async def handle_update(self, update: dict) -> None:
        message = update.get("message")
        callback = update.get("callback_query")
        questions = self._questions()

        if callback:
            chat_id = callback["from"]["id"]
            data = callback["data"]

            if data == "quiz:start":
                await self.answer_callback(callback["id"])
                await self._start_quiz(chat_id, questions)
            elif data == "quiz:top":
                await self.answer_callback(callback["id"])
                await self._show_leaderboard(chat_id)
            elif data == "quiz:help":
                await self.answer_callback(callback["id"])
                await self.send_message(chat_id, "ℹ️ \"O'yinni boshlash\" tugmasini bosing va to'g'ri javobni tanlang. Har to'g'ri javob uchun 10 ball!")
            elif data.startswith("quiz:answer:"):
                _, _, qidx_str, oidx_str = data.split(":")
                await self._handle_answer(chat_id, callback, questions, int(qidx_str), int(oidx_str))
            return

        if not message:
            return

        chat_id = message["chat"]["id"]
        text = (message.get("text") or "").strip()

        if text == "/start":
            await self.call_api(
                "sendMessage", chat_id=chat_id,
                text="🎉 <b>Qiziqarli viktorinaga xush kelibsiz!</b>\n\nBilimingizni sinab, ball to'plang va reytingda yuqoriga chiqing!",
                parse_mode="HTML",
                reply_markup=self._main_menu(),
            )
            return

        if text == "/top":
            await self._show_leaderboard(chat_id)

    async def _start_quiz(self, chat_id: int, questions: list[dict]) -> None:
        if not questions:
            await self.send_message(chat_id, "⚠️ Bu bot uchun hali savollar qo'shilmagan.")
            return

        progress = self.settings.setdefault("progress", {})
        progress[str(chat_id)] = {"index": 0, "score": 0}
        await self._persist()
        await self._send_question(chat_id, questions, 0)

    async def _send_question(self, chat_id: int, questions: list[dict], index: int) -> None:
        q = questions[index]
        buttons = [
            [{"text": opt, "callback_data": f"quiz:answer:{index}:{i}"}]
            for i, opt in enumerate(q["options"])
        ]
        await self.call_api(
            "sendMessage", chat_id=chat_id,
            text=f"❓ <b>{index + 1}-savol:</b>\n\n{q['question']}",
            parse_mode="HTML",
            reply_markup={"inline_keyboard": buttons},
        )

    async def _handle_answer(self, chat_id: int, callback: dict, questions: list[dict],
                              qidx: int, oidx: int) -> None:
        progress = self.settings.setdefault("progress", {})
        state = progress.get(str(chat_id))
        if state is None or state["index"] != qidx:
            await self.answer_callback(callback["id"], "Bu savol eskirgan.")
            return

        correct = questions[qidx]["correct_index"] == oidx
        if correct:
            state["score"] += 10
            await self.answer_callback(callback["id"], "✅ To'g'ri! +10 ball", show_alert=False)
        else:
            correct_text = questions[qidx]["options"][questions[qidx]["correct_index"]]
            await self.answer_callback(callback["id"], f"❌ Noto'g'ri. To'g'ri javob: {correct_text}", show_alert=True)

        next_index = qidx + 1
        if next_index < len(questions):
            state["index"] = next_index
            await self._persist()
            await self._send_question(chat_id, questions, next_index)
        else:
            leaderboard = self.settings.setdefault("leaderboard", {})
            key = str(chat_id)
            leaderboard[key] = max(leaderboard.get(key, 0), state["score"])
            progress.pop(key, None)
            await self._persist()
            await self.send_message(
                chat_id,
                f"🎉 <b>O'yin tugadi!</b>\n\n⭐ Yakuniy ball: {state['score']}\n\n"
                f"Qayta o'ynash uchun \"🎮 O'yinni boshlash\" tugmasini bosing.",
                reply_markup=self._main_menu(),
            )

    async def _show_leaderboard(self, chat_id: int) -> None:
        leaderboard = self.settings.get("leaderboard", {})
        top = sorted(leaderboard.items(), key=lambda x: x[1], reverse=True)[:10]
        if not top:
            await self.send_message(chat_id, "🏆 Hali hech kim o'ynamagan. Birinchi bo'ling!")
            return
        medals = ["🥇", "🥈", "🥉"]
        lines = []
        for i, (uid, score) in enumerate(top):
            medal = medals[i] if i < 3 else f"{i + 1}."
            lines.append(f"{medal} {uid} — {score} ball")
        await self.send_message(chat_id, "🏆 <b>TOP-10 o'yinchilar</b>\n\n" + "\n".join(lines))

    async def _persist(self) -> None:
        async with get_session() as session:
            await self.save_settings(session)
            await session.commit()
