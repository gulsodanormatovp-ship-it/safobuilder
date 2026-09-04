"""
Har bir kelgan xabar/callback uchun foydalanuvchi DB'da mavjudligini
tekshiradi va yo'q bo'lsa avtomatik yaratadi. Bu ayniqsa Render'ning
bepul tarifida SQLite fayli har deploy'da tozalanib ketganda tizimni
"NoResultFound" xatosidan asraydi.
"""
from aiogram import BaseMiddleware
from aiogram.types import TelegramObject
from sqlalchemy import select

from database.db import get_session
from database.models import User


class EnsureUserMiddleware(BaseMiddleware):
    async def __call__(self, handler, event: TelegramObject, data: dict):
        tg_user = data.get("event_from_user")
        if tg_user is not None:
            async with get_session() as session:
                result = await session.execute(
                    select(User).where(User.telegram_id == tg_user.id)
                )
                user = result.scalar_one_or_none()
                if user is None:
                    session.add(User(
                        telegram_id=tg_user.id,
                        username=tg_user.username,
                        full_name=tg_user.full_name,
                    ))
                    await session.commit()

        return await handler(event, data)
