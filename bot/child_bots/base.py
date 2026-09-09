"""
Har bir child-bot turi (Kino, Taxi, Anketa, ...) shu klassdan meros oladi.

Bu bazaviy klass ENDI har bir bot uchun umumiy "dahshatli" boshqaruv
imkoniyatlarini beradi (owner buyruqlari orqali):
  /block <id> /unblock <id>        — foydalanuvchini bloklash
  /broadcast <matn>                — ommaviy xabar / reklama
  /majburiy <@kanal>                — majburiy obuna kanalini o'rnatish
  /majburiyoff                      — majburiy obunani o'chirish
  /addadmin <id> /removeadmin <id> — botga qo'shimcha adminlar
  /adminlar                         — adminlar ro'yxati
  /balance+ <id> <summa>            — foydalanuvchi ichki balansiga qo'shish
  /balance- <id> <summa>            — foydalanuvchi ichki balansidan ayirish
  /reklama <matn> /reklamaoff       — muhim amaldan keyin ko'rsatiladigan reklama
"""
from __future__ import annotations

import json
import time
from abc import ABC, abstractmethod
from typing import Any

import httpx


class ChildBot(ABC):
    def __init__(self, bot_row) -> None:
        self.bot_row = bot_row
        self.token = bot_row.bot_token
        self.settings: dict[str, Any] = json.loads(bot_row.settings_json or "{}")
        self.api_base = f"https://api.telegram.org/bot{self.token}"

    async def call_api(self, method: str, **params) -> dict:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(f"{self.api_base}/{method}", json=params)
            return resp.json()

    async def send_message(self, chat_id: int, text: str, **kwargs) -> dict:
        return await self.call_api("sendMessage", chat_id=chat_id, text=text,
                                    parse_mode="HTML", **kwargs)

    async def answer_callback(self, callback_query_id: str, text: str = "", show_alert: bool = False) -> dict:
        return await self.call_api("answerCallbackQuery",
                                    callback_query_id=callback_query_id, text=text,
                                    show_alert=show_alert)

    @abstractmethod
    async def handle_update(self, update: dict) -> None:
        raise NotImplementedError

    async def save_settings(self, session) -> None:
        self.bot_row.settings_json = json.dumps(self.settings)
        session.add(self.bot_row)

    # ------------------------------------------------------------
    # Foydalanuvchilar, bloklash, spam-himoya
    # ------------------------------------------------------------

    def track_user(self, chat_id: int) -> None:
        known = self.settings.setdefault("known_users", [])
        if chat_id not in known:
            known.append(chat_id)

    def is_blocked(self, chat_id: int) -> bool:
        return chat_id in self.settings.get("blocked_users", [])

    def block_user(self, chat_id: int) -> None:
        blocked = self.settings.setdefault("blocked_users", [])
        if chat_id not in blocked:
            blocked.append(chat_id)

    def unblock_user(self, chat_id: int) -> None:
        blocked = self.settings.setdefault("blocked_users", [])
        if chat_id in blocked:
            blocked.remove(chat_id)

    def is_owner(self, chat_id: int) -> bool:
        return chat_id == self.settings.get("owner_telegram_id")

    def is_admin(self, chat_id: int) -> bool:
        """Owner + owner qo'shgan qo'shimcha adminlar."""
        return self.is_owner(chat_id) or chat_id in self.settings.get("admins", [])

    def get_ad_text(self) -> str | None:
        return self.settings.get("ad_text")

    def get_balance(self, chat_id: int) -> int:
        return self.settings.get("user_balances", {}).get(str(chat_id), 0)

    # ------------------------------------------------------------
    # Ball / daraja tizimi (barcha botlarda avtomatik ishlaydi)
    # ------------------------------------------------------------

    LEVELS = [
        (0, "🆕 Yangi"),
        (50, "🥉 Bronza"),
        (200, "🥈 Kumush"),
        (500, "🥇 Oltin"),
        (1000, "💎 Olmos"),
    ]

    def add_points(self, chat_id: int, amount: int = 1) -> None:
        points = self.settings.setdefault("user_points", {})
        key = str(chat_id)
        points[key] = points.get(key, 0) + amount

    def get_points(self, chat_id: int) -> int:
        return self.settings.get("user_points", {}).get(str(chat_id), 0)

    def get_level(self, chat_id: int) -> str:
        points = self.get_points(chat_id)
        level_name = self.LEVELS[0][1]
        for threshold, name in self.LEVELS:
            if points >= threshold:
                level_name = name
        return level_name

    def check_rate_limit(self, chat_id: int, max_per_10s: int = 5) -> bool:
        now = time.time()
        history = self.settings.setdefault("rate_limit", {})
        key = str(chat_id)
        timestamps = [t for t in history.get(key, []) if now - t < 10]
        timestamps.append(now)
        history[key] = timestamps[-20:]
        return len(timestamps) <= max_per_10s

    async def check_forced_subscription(self, chat_id: int) -> bool:
        """True — obuna talab qilinmaydi yoki foydalanuvchi allaqachon obuna."""
        required = self.settings.get("required_channel")
        if not required or self.is_owner(chat_id):
            return True
        result = await self.call_api("getChatMember", chat_id=required, user_id=chat_id)
        status = result.get("result", {}).get("status")
        return status in ("member", "administrator", "creator")

    async def send_forced_sub_prompt(self, chat_id: int) -> None:
        required = self.settings.get("required_channel", "")
        link = f"https://t.me/{required.lstrip('@')}"
        await self.call_api(
            "sendMessage", chat_id=chat_id,
            text="⚠️ Botdan foydalanish uchun avval quyidagi kanalga obuna bo'ling:",
            reply_markup={"inline_keyboard": [
                [{"text": "📢 Kanalga o'tish", "url": link}],
                [{"text": "✅ Tekshirish", "callback_data": "checksub"}],
            ]},
        )

    async def process_common_update(self, update: dict, session) -> bool:
        """
        Har bir update uchun umumiy tekshiruvlar: bloklash, spam-himoya,
        majburiy obuna. True — davom eting, False — e'tiborsiz qoldiring.
        """
        message = update.get("message") or {}
        callback = update.get("callback_query") or {}
        chat_id = (message.get("chat") or {}).get("id") or (callback.get("from") or {}).get("id")

        if chat_id is None:
            return True

        if self.is_blocked(chat_id):
            return False

        if not self.check_rate_limit(chat_id):
            return False

        # "Tekshirish" tugmasi bosilganda maxsus javob
        if callback.get("data") == "checksub":
            if await self.check_forced_subscription(chat_id):
                await self.answer_callback(callback["id"], "✅ Obuna tasdiqlandi! Botdan foydalanishingiz mumkin.", show_alert=True)
            else:
                await self.answer_callback(callback["id"], "❌ Hali obuna bo'lmagansiz.", show_alert=True)
            return False

        if not await self.check_forced_subscription(chat_id):
            await self.send_forced_sub_prompt(chat_id)
            return False

        self.track_user(chat_id)
        if message:
            self.add_points(chat_id, 1)
        await self.save_settings(session)
        await session.commit()
        return True

    async def handle_universal_user_commands(self, update: dict, session) -> bool:
        """
        HAR BIR foydalanuvchi (owner bo'lmasa ham) ishlata oladigan buyruqlar:
        /ballim, /reyting. True — shu yerda bajarildi, botga xos handle_update
        chaqirilmaydi.
        """
        message = update.get("message")
        if not message:
            return False

        chat_id = message["chat"]["id"]
        text = (message.get("text") or "").strip()

        if text == "/ballim":
            points = self.get_points(chat_id)
            level = self.get_level(chat_id)
            await self.send_message(chat_id, f"⭐ Ballaringiz: {points}\n🏅 Darajangiz: {level}")
            return True

        if text == "/reyting":
            points_map = self.settings.get("user_points", {})
            top = sorted(points_map.items(), key=lambda x: x[1], reverse=True)[:10]
            if not top:
                await self.send_message(chat_id, "🏆 Hali reyting bo'sh.")
                return True
            medals = ["🥇", "🥈", "🥉"]
            lines = [
                f"{medals[i] if i < 3 else f'{i + 1}.'} {uid} — {pts} ball"
                for i, (uid, pts) in enumerate(top)
            ]
            await self.send_message(chat_id, "🏆 <b>TOP-10 reyting</b>\n\n" + "\n".join(lines))
            return True

        return False

    async def handle_owner_commands(self, update: dict, session) -> bool:
        message = update.get("message")
        if not message:
            return False

        chat_id = message["chat"]["id"]
        text = (message.get("text") or "").strip()

        # Faqat owner: /addadmin, /removeadmin, /balance+, /balance-, /majburiy, /reklama
        if self.is_owner(chat_id):
            if text.startswith("/addadmin"):
                parts = text.split()
                if len(parts) == 2 and parts[1].isdigit():
                    admins = self.settings.setdefault("admins", [])
                    uid = int(parts[1])
                    if uid not in admins:
                        admins.append(uid)
                    await self.save_settings(session)
                    await session.commit()
                    await self.send_message(chat_id, f"✅ Admin qo'shildi: {uid}")
                else:
                    await self.send_message(chat_id, "ℹ️ Foydalanish: /addadmin <user_id>")
                return True

            if text.startswith("/removeadmin"):
                parts = text.split()
                if len(parts) == 2 and parts[1].isdigit():
                    admins = self.settings.setdefault("admins", [])
                    uid = int(parts[1])
                    if uid in admins:
                        admins.remove(uid)
                    await self.save_settings(session)
                    await session.commit()
                    await self.send_message(chat_id, f"✅ Admin olib tashlandi: {uid}")
                return True

            if text == "/adminlar":
                admins = self.settings.get("admins", [])
                lines = "\n".join(str(a) for a in admins) or "Qo'shimcha adminlar yo'q."
                await self.send_message(chat_id, f"👮 <b>Adminlar:</b>\n\n{lines}")
                return True

            if text.startswith("/balance+"):
                parts = text.split()
                if len(parts) == 3 and parts[1].isdigit() and parts[2].lstrip("-").isdigit():
                    balances = self.settings.setdefault("user_balances", {})
                    key = parts[1]
                    balances[key] = balances.get(key, 0) + int(parts[2])
                    await self.save_settings(session)
                    await session.commit()
                    await self.send_message(chat_id, f"✅ {parts[1]} balansiga {parts[2]} qo'shildi. Yangi balans: {balances[key]:,}".replace(",", " "))
                else:
                    await self.send_message(chat_id, "ℹ️ Foydalanish: /balance+ <user_id> <summa>")
                return True

            if text.startswith("/balance-"):
                parts = text.split()
                if len(parts) == 3 and parts[1].isdigit() and parts[2].isdigit():
                    balances = self.settings.setdefault("user_balances", {})
                    key = parts[1]
                    balances[key] = balances.get(key, 0) - int(parts[2])
                    await self.save_settings(session)
                    await session.commit()
                    await self.send_message(chat_id, f"✅ {parts[1]} balansidan {parts[2]} ayirildi. Yangi balans: {balances[key]:,}".replace(",", " "))
                else:
                    await self.send_message(chat_id, "ℹ️ Foydalanish: /balance- <user_id> <summa>")
                return True

            if text.startswith("/majburiyoff"):
                self.settings.pop("required_channel", None)
                await self.save_settings(session)
                await session.commit()
                await self.send_message(chat_id, "✅ Majburiy obuna o'chirildi.")
                return True

            if text.startswith("/majburiy"):
                parts = text.split()
                if len(parts) == 2 and parts[1].startswith("@"):
                    self.settings["required_channel"] = parts[1]
                    await self.save_settings(session)
                    await session.commit()
                    await self.send_message(chat_id, f"✅ Majburiy obuna kanali: {parts[1]}\n\n❗️ Botni shu kanalga admin qilib qo'shishni unutmang.")
                else:
                    await self.send_message(chat_id, "ℹ️ Foydalanish: /majburiy @kanal_username")
                return True

            if text.startswith("/reklamaoff"):
                self.settings.pop("ad_text", None)
                await self.save_settings(session)
                await session.commit()
                await self.send_message(chat_id, "✅ Reklama o'chirildi.")
                return True

            if text.startswith("/reklama"):
                ad_text = text[len("/reklama"):].strip()
                if not ad_text:
                    await self.send_message(chat_id, "ℹ️ Foydalanish: /reklama Matn")
                    return True
                self.settings["ad_text"] = ad_text
                await self.save_settings(session)
                await session.commit()
                await self.send_message(chat_id, "✅ Reklama o'rnatildi — muhim amallardan keyin ko'rsatiladi.")
                return True

        # Owner + adminlar uchun umumiy: block/unblock/broadcast
        if self.is_admin(chat_id):
            if text.startswith("/block"):
                parts = text.split()
                if len(parts) == 2 and parts[1].isdigit():
                    self.block_user(int(parts[1]))
                    await self.save_settings(session)
                    await session.commit()
                    await self.send_message(chat_id, f"⛔️ Foydalanuvchi bloklandi: {parts[1]}")
                else:
                    await self.send_message(chat_id, "ℹ️ Foydalanish: /block <user_id>")
                return True

            if text.startswith("/unblock"):
                parts = text.split()
                if len(parts) == 2 and parts[1].isdigit():
                    self.unblock_user(int(parts[1]))
                    await self.save_settings(session)
                    await session.commit()
                    await self.send_message(chat_id, f"✅ Bloklash bekor qilindi: {parts[1]}")
                else:
                    await self.send_message(chat_id, "ℹ️ Foydalanish: /unblock <user_id>")
                return True

            if text.startswith("/broadcast"):
                broadcast_text = text[len("/broadcast"):].strip()
                if not broadcast_text:
                    await self.send_message(chat_id, "ℹ️ Foydalanish: /broadcast Xabar matni")
                    return True

                known_users = self.settings.get("known_users", [])
                sent = 0
                for uid in known_users:
                    if uid == chat_id or self.is_blocked(uid):
                        continue
                    try:
                        await self.send_message(uid, broadcast_text)
                        sent += 1
                    except Exception:
                        pass

                await self.send_message(chat_id, f"✅ Xabar {sent} ta foydalanuvchiga yuborildi.")
                return True

        return False
