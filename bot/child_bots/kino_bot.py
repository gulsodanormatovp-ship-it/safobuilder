import random
import string
from datetime import datetime, timedelta

from database.db import get_session
from .base import ChildBot


def _generate_code(length: int = 6) -> str:
    return "".join(random.choices(string.digits, k=length))


class KinoBot(ChildBot):
    """
    Owner/admin botga video yuboradi -> bot random kod beradi.
    Foydalanuvchilar UCHUN obuna tizimi:
      - Ro'yxatdan o'tgan kundan boshlab N kun (trial_days, default 3) BEPUL.
      - Sinov tugagach, subscription_price so'm / subscription_days kunlik
        obuna kerak (default 29 990 so'm / 15 kun).
      - To'lov: foydalanuvchi chek yuboradi -> owner tasdiqlaydi -> obuna faollashadi.
    Owner sozlaydigan narxlar Mini App > Sozlash bo'limidan yoki
    /obunanarxi <narx> <kun> buyrug'i orqali o'zgartiriladi.
    Kanalga avtopost: settings["post_channel_id"] o'rnatilsa, har yangi kino
    qo'shilganda o'sha kanalga deep-link bilan post qilinadi.
    """

    DEFAULT_TRIAL_DAYS = 3
    DEFAULT_SUB_PRICE = 29_990
    DEFAULT_SUB_DAYS = 15

    def _main_menu(self, is_owner: bool) -> dict:
        rows = [
            [{"text": "🔎 Kino qidirish", "callback_data": "kino:search"}],
            [{"text": "🆕 Yangi kinolar", "callback_data": "kino:latest"}],
            [{"text": "💎 Obunam", "callback_data": "kino:mysub"}],
            [{"text": "ℹ️ Yordam", "callback_data": "kino:help"}],
        ]
        if is_owner:
            rows.append([{"text": "📊 Statistikam", "callback_data": "kino:stats"}])
        return {"inline_keyboard": rows}

    # ---------------- Obuna holatini tekshirish ----------------

    def _trial_days(self) -> int:
        return self.settings.get("trial_days", self.DEFAULT_TRIAL_DAYS)

    def _sub_price(self) -> int:
        return self.settings.get("subscription_price", self.DEFAULT_SUB_PRICE)

    def _sub_days(self) -> int:
        return self.settings.get("subscription_days", self.DEFAULT_SUB_DAYS)

    def _ensure_registered(self, chat_id: int) -> None:
        registered = self.settings.setdefault("user_registered_at", {})
        if str(chat_id) not in registered:
            registered[str(chat_id)] = datetime.utcnow().isoformat()

    def _has_access(self, chat_id: int) -> bool:
        if self.is_admin(chat_id):
            return True
        registered = self.settings.get("user_registered_at", {})
        reg_str = registered.get(str(chat_id))
        if reg_str:
            reg_time = datetime.fromisoformat(reg_str)
            if datetime.utcnow() < reg_time + timedelta(days=self._trial_days()):
                return True  # hali sinov muddatida
        subs = self.settings.get("user_subscription_expires", {})
        exp_str = subs.get(str(chat_id))
        if exp_str and datetime.fromisoformat(exp_str) > datetime.utcnow():
            return True
        return False

    async def _send_paywall(self, chat_id: int) -> None:
        price = self._sub_price()
        days = self._sub_days()
        card = self.settings.get("payment_card_number", "— (owner hali sozlamagan)")
        await self.call_api(
            "sendMessage", chat_id=chat_id,
            text=(
                f"⏳ Bepul sinov muddatingiz tugadi.\n\n"
                f"💎 Obuna: {price:,} so'm / {days} kun".replace(",", " ") + "\n\n"
                f"💳 Karta: <code>{card}</code>\n\n"
                f"To'lov qilgach, chek skrinshotini shu yerga yuboring."
            ),
            parse_mode="HTML",
        )

    # ---------------- Asosiy oqim ----------------

    async def handle_update(self, update: dict) -> None:
        message = update.get("message")
        callback = update.get("callback_query")

        if callback:
            chat_id = callback["from"]["id"]
            data = callback["data"]

            if data == "kino:search":
                await self.answer_callback(callback["id"])
                await self.send_message(chat_id, "🔎 Kino kodini yuboring (masalan: 482913)")
            elif data == "kino:latest":
                movies = self.settings.get("movies", {})
                last_codes = list(movies.keys())[-5:]
                text = ("🆕 Oxirgi qo'shilgan kodlar:\n\n" + "\n".join(f"🔑 {c}" for c in last_codes)) \
                    if last_codes else "Hozircha kino yo'q."
                await self.answer_callback(callback["id"])
                await self.send_message(chat_id, text)
            elif data == "kino:help":
                await self.answer_callback(callback["id"])
                await self.send_message(chat_id, "ℹ️ Kino kodini yuboring — bot filmni avtomatik topib beradi.")
            elif data == "kino:mysub":
                await self.answer_callback(callback["id"])
                if self._has_access(chat_id):
                    await self.send_message(chat_id, "✅ Obunangiz faol — kinolardan bemalol foydalanishingiz mumkin.")
                else:
                    await self._send_paywall(chat_id)
            elif data == "kino:stats" and self.is_owner(chat_id):
                movies = self.settings.get("movies", {})
                active_subs = sum(
                    1 for exp in self.settings.get("user_subscription_expires", {}).values()
                    if datetime.fromisoformat(exp) > datetime.utcnow()
                )
                await self.answer_callback(callback["id"])
                await self.send_message(
                    chat_id,
                    f"📊 Jami kinolar: {len(movies)} ta\n💎 Faol obunachilar: {active_subs} ta",
                )
            elif data.startswith("kinopay:approve:"):
                await self._approve_payment(int(data.split(":")[2]), callback)
            elif data.startswith("kinopay:reject:"):
                target = int(data.split(":")[2])
                await self.answer_callback(callback["id"], "Rad etildi")
                await self.send_message(target, "❌ To'lov chekingiz rad etildi.")
            return

        if not message:
            return

        chat_id = message["chat"]["id"]

        if "video" in message and self.is_admin(chat_id):
            await self._save_movie(message, chat_id)
            return

        if "photo" in message and not self.is_admin(chat_id) and not self._has_access(chat_id):
            await self._submit_payment_receipt(message, chat_id)
            return

        text = (message.get("text") or "").strip()

        if text.startswith("/obunanarxi") and self.is_owner(chat_id):
            parts = text.split()
            if len(parts) == 3 and parts[1].isdigit() and parts[2].isdigit():
                self.settings["subscription_price"] = int(parts[1])
                self.settings["subscription_days"] = int(parts[2])
                async with get_session() as session:
                    await self.save_settings(session)
                    await session.commit()
                await self.send_message(chat_id, f"✅ Obuna narxi: {parts[1]} so'm / {parts[2]} kun")
            else:
                await self.send_message(chat_id, "ℹ️ Foydalanish: /obunanarxi <narx> <kun>")
            return

        if text.startswith("/karta") and self.is_owner(chat_id):
            card = text[len("/karta"):].strip()
            self.settings["payment_card_number"] = card
            async with get_session() as session:
                await self.save_settings(session)
                await session.commit()
            await self.send_message(chat_id, "✅ Karta raqami saqlandi.")
            return

        if text.startswith("/kanalpost") and self.is_owner(chat_id):
            parts = text.split()
            if len(parts) == 2 and parts[1].startswith("@"):
                self.settings["post_channel"] = parts[1]
                async with get_session() as session:
                    await self.save_settings(session)
                    await session.commit()
                await self.send_message(chat_id, f"✅ Kanalga avtopost yoqildi: {parts[1]}\n❗️ Botni shu kanalga admin qiling.")
            else:
                await self.send_message(chat_id, "ℹ️ Foydalanish: /kanalpost @kanal_username")
            return

        if text == "/start" or text.startswith("/start code_"):
            self._ensure_registered(chat_id)
            async with get_session() as session:
                await self.save_settings(session)
                await session.commit()

            if text.startswith("/start code_"):
                code = text.split("code_", 1)[1].strip()
                if code in self.settings.get("movies", {}):
                    if not self._has_access(chat_id):
                        await self._send_paywall(chat_id)
                        return
                    movie = self.settings["movies"][code]
                    await self.call_api(
                        "copyMessage", chat_id=chat_id,
                        from_chat_id=movie["chat_id"], message_id=movie["message_id"],
                    )
                    return

            await self.call_api(
                "sendMessage", chat_id=chat_id,
                text="🎬 <b>Xush kelibsiz!</b>\n\nKino kodini yuboring yoki quyidagi tugmalardan foydalaning:",
                parse_mode="HTML",
                reply_markup=self._main_menu(self.is_owner(chat_id)),
            )
            return

        if text.isdigit() and text in self.settings.get("movies", {}):
            if not self._has_access(chat_id):
                await self._send_paywall(chat_id)
                return

            movie = self.settings["movies"][text]
            await self.call_api(
                "copyMessage", chat_id=chat_id,
                from_chat_id=movie["chat_id"], message_id=movie["message_id"],
            )
            ad = self.get_ad_text()
            if ad:
                await self.send_message(chat_id, f"📢 {ad}")
            return

        if text.isdigit():
            await self.send_message(chat_id, "❌ Bunday kodli kino topilmadi.")

    # ---------------- Kino saqlash + kanalga avtopost ----------------

    async def _save_movie(self, message: dict, owner_chat_id: int) -> None:
        code = _generate_code()
        self.settings.setdefault("movies", {})[code] = {
            "chat_id": owner_chat_id,
            "message_id": message["message_id"],
            "added_at": datetime.utcnow().isoformat(),
        }
        async with get_session() as session:
            await self.save_settings(session)
            await session.commit()

        await self.send_message(owner_chat_id, f"✅ Film saqlandi!\n🔑 Kod: <code>{code}</code>")

        post_channel = self.settings.get("post_channel")
        if post_channel:
            bot_username = self.bot_row.bot_username
            deep_link = f"https://t.me/{bot_username}?start=code_{code}"
            await self.call_api(
                "sendMessage", chat_id=post_channel,
                text=f"🎬 <b>Yangi kino qo'shildi!</b>\n\n🔑 Kod: <code>{code}</code>",
                parse_mode="HTML",
                reply_markup={"inline_keyboard": [[{"text": "▶️ Ko'rish", "url": deep_link}]]},
            )

    # ---------------- To'lov: chek qabul qilish va tasdiqlash ----------------

    async def _submit_payment_receipt(self, message: dict, chat_id: int) -> None:
        owner_id = self.settings.get("owner_telegram_id")
        if not owner_id:
            return
        await self.call_api(
            "sendPhoto", chat_id=owner_id,
            photo=message["photo"][-1]["file_id"],
            caption=f"🧾 Yangi obuna cheki (user {chat_id})\n💎 {self._sub_price():,} so'm / {self._sub_days()} kun".replace(",", " "),
            reply_markup={"inline_keyboard": [[
                {"text": "✅ Tasdiqlash", "callback_data": f"kinopay:approve:{chat_id}"},
                {"text": "❌ Rad etish", "callback_data": f"kinopay:reject:{chat_id}"},
            ]]},
        )
        await self.send_message(chat_id, "✅ Chekingiz admin ko'rib chiqishga yuborildi.")

    async def _approve_payment(self, target_id: int, callback: dict) -> None:
        subs = self.settings.setdefault("user_subscription_expires", {})
        key = str(target_id)
        base = datetime.utcnow()
        if key in subs and datetime.fromisoformat(subs[key]) > base:
            base = datetime.fromisoformat(subs[key])
        subs[key] = (base + timedelta(days=self._sub_days())).isoformat()

        async with get_session() as session:
            await self.save_settings(session)
            await session.commit()

        await self.answer_callback(callback["id"], "Tasdiqlandi ✅")
        await self.send_message(
            target_id,
            f"✅ Obunangiz faollashtirildi! {self._sub_days()} kun davomida kinolardan foydalanishingiz mumkin.",
        )
