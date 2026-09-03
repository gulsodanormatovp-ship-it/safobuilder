"""
Har bir child-bot turi (Kino, Taxi, Anketa, ...) shu klassdan meros oladi.
Runtime router (api/main.py) kelgan Telegram update'ni shu obyektning
`handle_update` metodiga uzatadi — qaysi bot turi ekanini bilishning
o'zi kifoya, qolgan hammasi bot ichida hal bo'ladi.
"""
from __future__ import annotations

import json
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
