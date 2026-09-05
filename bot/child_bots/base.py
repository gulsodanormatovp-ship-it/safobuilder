"""
Har bir child-bot turi (Kino, Taxi, Anketa, ...) shu klassdan meros oladi.
Runtime router (api/main.py) kelgan Telegram update'ni shu obyektning
`handle_update` metodiga uzatadi — qaysi bot turi ekanini bilishning
o'zi kifoya, qolgan hammasi bot ichida hal bo'ladi.

Bu bazaviy klass endi barcha bot turlari uchun umumiy bo'lgan narsalarni
ham o'z ichiga oladi: foydalanuvchilar ro'yxatini kuzatish (broadcast
uchun), bloklangan foydalanuvchilarni tekshirish, va spam-himoya.
"""
from __future__ import annotations

import json
import time
from abc import ABC, abstractmethod
from typing import Any

import httpx


class ChildBot(ABC):
    def __init__(self, bot_row) -> None:
        self.bot_row = bot_row          # database.models.Bot qatori
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

    async def answer_callback(self, callback_query_id: str, text: str = "") -> dict:
        return await self.call_api("answerCallbackQuery",
                                    callback_query_id=callback_query_id, text=text)

    @abstractmethod
    async def handle_update(self, update: dict) -> None:
        """Har bir bot turi o'z mantig'ini shu yerda amalga oshiradi."""
        raise NotImplementedError

    async def save_settings(self, session) -> None:
        self.bot_row.settings_json = json.dumps(self.settings)
        session.add(self.bot_row)

    # ------------------------------------------------------------
    # Umumiy funksiyalar: foydalanuvchilar ro'yxati, bloklash, spam himoya
    # ------------------------------------------------------------

    def track_user(self, chat_id: int) -> None:
        """Broadcast uchun — bot bilan gaplashgan har bir userni ro'yxatga oladi."""
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

    def check_rate_limit(self, chat_id: int, max_per_10s: int = 5) -> bool:
        """True qaytarsa — foydalanuvchi ruxsat etilgan chegarada. False — spam qilyapti."""
        now = time.time()
        history = self.settings.setdefault("rate_limit", {})
        key = str(chat_id)
        timestamps = [t for t in history.get(key, []) if now - t < 10]
        timestamps.append(now)
        history[key] = timestamps[-20:]  # xotira shishib ketmasligi uchun cheklov
        return len(timestamps) <= max_per_10s

    async def process_common_update(self, update: dict, session) -> bool:
        """
        Har bir handle_update boshida chaqiriladi. True qaytarsa — davom eting,
        False qaytarsa — foydalanuvchi bloklangan yoki spam qilyapti, e'tiborsiz qoldiring.
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

        self.track_user(chat_id)
        await self.save_settings(session)
        await session.commit()
        return True

    async def handle_owner_commands(self, update: dict, session) -> bool:
        """
        Owner uchun universal buyruqlar — barcha bot turlarida ishlaydi:
        /block <id>, /unblock <id>, /broadcast <matn>.
        True qaytarsa — buyruq shu yerda bajarildi, botga xos handle_update
        chaqirilmaydi. False — oddiy xabar, davom eting.
        """
        message = update.get("message")
        if not message:
            return False

        chat_id = message["chat"]["id"]
        if chat_id != self.settings.get("owner_telegram_id"):
            return False

        text = (message.get("text") or "").strip()

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
