"""
FastAPI ilovasi endi UCHTA vazifani bajaradi (Render bepul tarifida
bitta Web Service ichida ishlashi uchun):

1. `/platform-webhook` — SafoBuilder (platforma) botining o'zi shu yerga
   webhook orqali ulanadi (polling emas) — shu tufayli alohida
   "Background Worker" (pullik xizmat) kerak bo'lmaydi.
2. `/webhook/{bot_id}` — foydalanuvchilar yaratgan child botlar shu yerga tushadi.
3. `/api/*` — Mini App uchun REST API, `/webapp` — Mini App statik fayllari.
"""
import csv
import hashlib
import hmac
import io
import json
import os
from datetime import datetime, timedelta
from urllib.parse import parse_qsl

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import Update
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import select

from bot.child_bots import BOT_TYPE_REGISTRY
from bot.handlers import bot_settings, create_bot, my_bots, payment, profile, start
from bot.middlewares import EnsureUserMiddleware
from database.db import get_session, init_db
from database.models import Bot as BotModel, BotStat, User

PLATFORM_BOT_TOKEN = os.getenv("PLATFORM_BOT_TOKEN", "")
PUBLIC_BASE_URL = os.getenv("PUBLIC_BASE_URL", "")

app = FastAPI(title="SafoBuilder API")
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"],
)
app.mount("/webapp", StaticFiles(directory="webapp", html=True), name="webapp")

# ------------------------------------------------------------------
# Platforma botini webhook rejimida sozlash
# ------------------------------------------------------------------
platform_bot = Bot(
    token=PLATFORM_BOT_TOKEN,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML),
) if PLATFORM_BOT_TOKEN else None

dp = Dispatcher(storage=MemoryStorage())
dp.update.outer_middleware(EnsureUserMiddleware())

dp.include_router(start.router)
dp.include_router(create_bot.router)
dp.include_router(my_bots.router)
dp.include_router(bot_settings.router)
dp.include_router(payment.router)
dp.include_router(profile.router)


@app.on_event("startup")
async def on_startup() -> None:
    await init_db()
    if platform_bot and PUBLIC_BASE_URL:
        await platform_bot.set_webhook(f"{PUBLIC_BASE_URL}/platform-webhook")


@app.post("/platform-webhook")
async def platform_webhook(request: Request) -> dict:
    if platform_bot is None:
        raise HTTPException(status_code=500, detail="PLATFORM_BOT_TOKEN sozlanmagan")
    data = await request.json()
    update = Update.model_validate(data)
    await dp.feed_webhook_update(platform_bot, update)
    return {"ok": True}


# ------------------------------------------------------------------
# 1) Child bot webhooklari
# ------------------------------------------------------------------

@app.post("/webhook/{bot_id}")
async def child_bot_webhook(bot_id: int, request: Request) -> dict:
    update = await request.json()

    async with get_session() as session:
        result = await session.execute(select(BotModel).where(BotModel.id == bot_id))
        bot_row = result.scalar_one_or_none()

    if bot_row is None:
        raise HTTPException(status_code=404, detail="Bot topilmadi")

    handler_cls = BOT_TYPE_REGISTRY.get(bot_row.bot_type)
    if handler_cls is None:
        return {"ok": True, "note": f"{bot_row.bot_type} turi hali qo'llab-quvvatlanmaydi"}

    child_bot = handler_cls(bot_row)
    await child_bot.handle_update(update)
    await _record_activity(bot_id, update)
    return {"ok": True}


async def _record_activity(bot_id: int, update: dict) -> None:
    today = datetime.utcnow().date()
    async with get_session() as session:
        result = await session.execute(
            select(BotStat).where(BotStat.bot_id == bot_id, BotStat.date == today)
        )
        stat = result.scalar_one_or_none()
        if stat is None:
            stat = BotStat(bot_id=bot_id, date=today)
            session.add(stat)

        if "message" in update:
            stat.messages += 1
        if update.get("message", {}).get("text") == "/start":
            stat.new_users += 1
        if "callback_query" in update:
            stat.requests += 1

        await session.commit()


# ------------------------------------------------------------------
# 2) Mini App REST API
# ------------------------------------------------------------------

def verify_telegram_webapp_data(init_data: str) -> dict:
    parsed = dict(parse_qsl(init_data))
    received_hash = parsed.pop("hash", None)
    if not received_hash:
        raise HTTPException(status_code=401, detail="initData yaroqsiz")

    data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(parsed.items()))
    secret_key = hmac.new(b"WebAppData", PLATFORM_BOT_TOKEN.encode(), hashlib.sha256).digest()
    computed_hash = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()

    if not hmac.compare_digest(computed_hash, received_hash):
        raise HTTPException(status_code=401, detail="initData imzosi mos kelmadi")

    return json.loads(parsed.get("user", "{}"))


@app.get("/api/bots/{bot_id}")
async def get_bot_public_info(bot_id: int) -> dict:
    async with get_session() as session:
        result = await session.execute(select(BotModel).where(BotModel.id == bot_id))
        bot_row = result.scalar_one_or_none()

    if bot_row is None:
        raise HTTPException(status_code=404, detail="Bot topilmadi")

    settings = json.loads(bot_row.settings_json or "{}")
    return {
        "id": bot_row.id,
        "type": bot_row.bot_type,
        "display_name": bot_row.display_name,
        "username": bot_row.bot_username,
        "tariff": bot_row.tariff,
        "status": bot_row.status,
        "questions": settings.get("questions", []) if bot_row.bot_type == "anketa" else None,
    }


@app.get("/api/bots/{bot_id}/stats")
async def bot_stats(bot_id: int, range: str = "today") -> dict:
    days = {"today": 1, "week": 7, "month": 30}.get(range, 1)
    since = datetime.utcnow().date() - timedelta(days=days - 1)

    async with get_session() as session:
        result = await session.execute(
            select(BotStat).where(BotStat.bot_id == bot_id, BotStat.date >= since)
            .order_by(BotStat.date)
        )
        rows = result.scalars().all()

    return {
        "bot_id": bot_id,
        "range": range,
        "series": [
            {
                "date": r.date.isoformat(),
                "new_users": r.new_users,
                "messages": r.messages,
                "requests": r.requests,
                "errors": r.errors,
                "undelivered": r.undelivered,
            }
            for r in rows
        ],
    }


@app.get("/api/me")
async def get_me(init_data: str) -> dict:
    tg_user = verify_telegram_webapp_data(init_data)
    async with get_session() as session:
        result = await session.execute(
            select(User).where(User.telegram_id == tg_user["id"])
        )
        user = result.scalar_one_or_none()
        if user is None:
            raise HTTPException(status_code=404, detail="Foydalanuvchi topilmadi")

        bots_result = await session.execute(select(BotModel).where(BotModel.owner_id == user.id))
        bots = bots_result.scalars().all()

    return {
        "telegram_id": user.telegram_id,
        "balance": user.balance,
        "bots": [
            {"id": b.id, "username": b.bot_username, "type": b.bot_type, "status": b.status}
            for b in bots
        ],
    }


@app.get("/api/bots/{bot_id}/anketa-export")
async def export_anketa(bot_id: int) -> StreamingResponse:
    async with get_session() as session:
        result = await session.execute(select(BotModel).where(BotModel.id == bot_id))
        bot_row = result.scalar_one_or_none()

    if bot_row is None or bot_row.bot_type != "anketa":
        raise HTTPException(status_code=404, detail="Anketa bot topilmadi")

    settings = json.loads(bot_row.settings_json or "{}")
    questions = settings.get("questions", [])
    responses = settings.get("responses", {})

    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["user_id", *questions])
    for user_id, data in responses.items():
        writer.writerow([user_id, *data.get("answers", [])])
    buffer.seek(0)

    return StreamingResponse(
        iter([buffer.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=anketa_{bot_id}.csv"},
    )


@app.get("/")
async def health_check() -> dict:
    """Render'ning \"health check\" so'rovlari uchun — xizmat tirikligini bildiradi."""
    return {"status": "ok", "service": "SafoBuilder API"}
