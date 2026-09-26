"""
FastAPI ilovasi Render bepul tarifida bitta Web Service ichida hammasini
bajaradi:

1. `/platform-webhook` — Vezto (platforma) botining o'zi shu yerga webhook
   orqali ulanadi (polling emas) — alohida "Background Worker" kerak emas.
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

import httpx
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import Update
from fastapi import BackgroundTasks, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from sqlalchemy import func, select

from bot.child_bots import BOT_TYPE_REGISTRY
from bot.handlers import admin_panel, bot_settings, create_bot, my_bots, payment, profile, start
from bot.middlewares import EnsureUserMiddleware
from bot.platform_settings import get_effective_catalog
from bot.tariffs import TARIFFS
from database.db import get_session, init_db
from database.models import Bot as BotModel, BotStat, Referral, User

PLATFORM_BOT_TOKEN = os.getenv("PLATFORM_BOT_TOKEN", "")
PUBLIC_BASE_URL = os.getenv("PUBLIC_BASE_URL", "")

# ------------------------------------------------------------------
# Takroriy (duplicate) update'larning oldini olish.
#
# Render'ning bepul tarifida server "uxlab" qolgan bo'lsa, birinchi so'rov
# uyg'onishni kutayotganda 10+ soniya cho'zilishi mumkin. Agar Telegram
# 200 OK javobini kutib ulgurmasa, xuddi shu update'ni QAYTA yuboradi —
# natijada bot bir xil xabarni bir necha marta jo'natgandek ko'rinadi.
# Buning yechimi ikki qavatli:
#   1) Telegramga DARHOL 200 OK qaytaramiz, haqiqiy ishni orqa fonda bajaramiz.
#   2) Har bir update_id'ni xotirada belgilab, ikkinchi marta kelsa
#      butunlay e'tiborsiz qoldiramiz.
# ------------------------------------------------------------------
_seen_update_keys: set[str] = set()
_seen_update_order: list[str] = []
_MAX_TRACKED_UPDATES = 5000


def _is_duplicate_update(scope: str, update_id: int | None) -> bool:
    if update_id is None:
        return False
    key = f"{scope}:{update_id}"
    if key in _seen_update_keys:
        return True
    _seen_update_keys.add(key)
    _seen_update_order.append(key)
    if len(_seen_update_order) > _MAX_TRACKED_UPDATES:
        oldest = _seen_update_order.pop(0)
        _seen_update_keys.discard(oldest)
    return False


app = FastAPI(title="Vezto API")
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

dp.include_router(admin_panel.router)
dp.include_router(start.router)
dp.include_router(create_bot.router)
dp.include_router(my_bots.router)
dp.include_router(bot_settings.router)
dp.include_router(payment.router)
dp.include_router(profile.router)

platform_bot_username_cache: dict[str, str] = {}


@app.on_event("startup")
async def on_startup() -> None:
    await init_db()
    if platform_bot and PUBLIC_BASE_URL:
        await platform_bot.set_webhook(f"{PUBLIC_BASE_URL}/platform-webhook")
    if platform_bot:
        me = await platform_bot.get_me()
        platform_bot_username_cache["username"] = me.username


@app.post("/platform-webhook")
async def platform_webhook(request: Request, background_tasks: BackgroundTasks) -> dict:
    if platform_bot is None:
        raise HTTPException(status_code=500, detail="PLATFORM_BOT_TOKEN sozlanmagan")

    data = await request.json()
    if _is_duplicate_update("platform", data.get("update_id")):
        return {"ok": True, "note": "duplicate, skipped"}

    background_tasks.add_task(_process_platform_update, data)
    return {"ok": True}


async def _process_platform_update(data: dict) -> None:
    update = Update.model_validate(data)
    await dp.feed_webhook_update(platform_bot, update)


# ------------------------------------------------------------------
# 1) Child bot webhooklari
# ------------------------------------------------------------------

@app.post("/webhook/{bot_id}")
async def child_bot_webhook(bot_id: int, request: Request, background_tasks: BackgroundTasks) -> dict:
    update = await request.json()

    if _is_duplicate_update(f"bot{bot_id}", update.get("update_id")):
        return {"ok": True, "note": "duplicate, skipped"}

    background_tasks.add_task(_process_child_bot_update, bot_id, update)
    return {"ok": True}


async def _process_child_bot_update(bot_id: int, update: dict) -> None:
    async with get_session() as session:
        result = await session.execute(select(BotModel).where(BotModel.id == bot_id))
        bot_row = result.scalar_one_or_none()

    if bot_row is None:
        return

    if bot_row.expires_at and bot_row.expires_at < datetime.utcnow():
        chat_id = (
            (update.get("message") or {}).get("chat", {}).get("id")
            or (update.get("callback_query") or {}).get("from", {}).get("id")
        )
        if chat_id:
            async with httpx.AsyncClient(timeout=10) as client:
                await client.post(
                    f"https://api.telegram.org/bot{bot_row.bot_token}/sendMessage",
                    json={
                        "chat_id": chat_id,
                        "text": "⏳ Ushbu botning obuna muddati tugagan. "
                                "Bot egasi Vezto platformasida tarifni "
                                "yangilashi kerak.",
                    },
                )
        return

    handler_cls = BOT_TYPE_REGISTRY.get(bot_row.bot_type)
    if handler_cls is None:
        return

    child_bot = handler_cls(bot_row)
    async with get_session() as session:
        allowed = await child_bot.process_common_update(update, session)
    if not allowed:
        return

    async with get_session() as session:
        handled = await child_bot.handle_owner_commands(update, session)
    if handled:
        return

    async with get_session() as session:
        handled = await child_bot.handle_universal_user_commands(update, session)
    if handled:
        return

    await child_bot.handle_update(update)
    await _record_activity(bot_id, update)


async def _record_activity(bot_id: int, update: dict) -> None:
    """Statistikani (Mini App dashboardidagi grafik) yangilaydi."""
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
    """
    Telegram Mini App yuboradigan `initData`ni tekshiradi (rasmiy algoritm:
    https://core.telegram.org/bots/webapps#validating-data-received-via-the-mini-app).
    """
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
        "theme_color": settings.get("theme_color", "#6366f1"),
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


async def _get_owned_bot(bot_id: int, init_data: str) -> BotModel:
    """Bot mavjudligini va so'rovchi haqiqatan uning egasi ekanini tekshiradi."""
    tg_user = verify_telegram_webapp_data(init_data)
    async with get_session() as session:
        result = await session.execute(select(BotModel).where(BotModel.id == bot_id))
        bot_row = result.scalar_one_or_none()
        if bot_row is None:
            raise HTTPException(status_code=404, detail="Bot topilmadi")

        owner_result = await session.execute(select(User).where(User.id == bot_row.owner_id))
        owner = owner_result.scalar_one()
        if owner.telegram_id != tg_user.get("id"):
            raise HTTPException(status_code=403, detail="Bu botga ruxsatingiz yo'q")

    return bot_row


@app.get("/api/bots/{bot_id}/users")
async def list_bot_users(bot_id: int, init_data: str) -> dict:
    bot_row = await _get_owned_bot(bot_id, init_data)
    settings = json.loads(bot_row.settings_json or "{}")
    blocked = set(settings.get("blocked_users", []))
    known = settings.get("known_users", [])
    return {
        "total": len(known),
        "blocked_count": len(blocked),
        "users": [{"id": uid, "blocked": uid in blocked} for uid in known],
    }


class BroadcastRequest(BaseModel):
    init_data: str
    text: str


@app.post("/api/bots/{bot_id}/broadcast")
async def broadcast_via_miniapp(bot_id: int, payload: BroadcastRequest) -> dict:
    bot_row = await _get_owned_bot(bot_id, payload.init_data)
    settings = json.loads(bot_row.settings_json or "{}")
    blocked = set(settings.get("blocked_users", []))
    known = settings.get("known_users", [])

    sent = 0
    async with httpx.AsyncClient(timeout=10) as client:
        for uid in known:
            if uid in blocked:
                continue
            try:
                resp = await client.post(
                    f"https://api.telegram.org/bot{bot_row.bot_token}/sendMessage",
                    json={"chat_id": uid, "text": payload.text},
                )
                if resp.json().get("ok"):
                    sent += 1
            except Exception:
                pass

    return {"sent": sent, "total": len(known)}


class UserActionRequest(BaseModel):
    init_data: str
    user_id: int


@app.post("/api/bots/{bot_id}/block")
async def block_user_via_miniapp(bot_id: int, payload: UserActionRequest) -> dict:
    await _get_owned_bot(bot_id, payload.init_data)
    async with get_session() as session:
        result = await session.execute(select(BotModel).where(BotModel.id == bot_id))
        fresh_row = result.scalar_one()
        settings = json.loads(fresh_row.settings_json or "{}")
        blocked = settings.setdefault("blocked_users", [])
        if payload.user_id not in blocked:
            blocked.append(payload.user_id)
        fresh_row.settings_json = json.dumps(settings)
        await session.commit()
    return {"ok": True}


@app.post("/api/bots/{bot_id}/unblock")
async def unblock_user_via_miniapp(bot_id: int, payload: UserActionRequest) -> dict:
    await _get_owned_bot(bot_id, payload.init_data)
    async with get_session() as session:
        result = await session.execute(select(BotModel).where(BotModel.id == bot_id))
        fresh_row = result.scalar_one()
        settings = json.loads(fresh_row.settings_json or "{}")
        blocked = settings.setdefault("blocked_users", [])
        if payload.user_id in blocked:
            blocked.remove(payload.user_id)
        fresh_row.settings_json = json.dumps(settings)
        await session.commit()
    return {"ok": True}


EDITABLE_SETTINGS_KEYS = (
    "questions", "driver_group_id", "price", "channel_id",
    "prize_text", "bonus_per_invite", "services", "candidates",
    "kitchen_group_id", "required_channel", "ad_text",
    "subscription_price", "subscription_days", "trial_days",
    "payment_card_number", "post_channel", "quiz_questions",
    "theme_color", "products",
)


@app.get("/api/bots/{bot_id}/settings")
async def get_bot_settings(bot_id: int, init_data: str) -> dict:
    bot_row = await _get_owned_bot(bot_id, init_data)
    settings = json.loads(bot_row.settings_json or "{}")
    return {"settings": {k: v for k, v in settings.items() if k in EDITABLE_SETTINGS_KEYS}}


class SettingsUpdateRequest(BaseModel):
    init_data: str
    settings: dict


@app.post("/api/bots/{bot_id}/settings")
async def update_bot_settings(bot_id: int, payload: SettingsUpdateRequest) -> dict:
    await _get_owned_bot(bot_id, payload.init_data)
    async with get_session() as session:
        result = await session.execute(select(BotModel).where(BotModel.id == bot_id))
        fresh_row = result.scalar_one()
        settings = json.loads(fresh_row.settings_json or "{}")
        for key, value in payload.settings.items():
            if key in EDITABLE_SETTINGS_KEYS:
                settings[key] = value
        fresh_row.settings_json = json.dumps(settings)
        await session.commit()
    return {"ok": True}


@app.get("/api/bots/{bot_id}/subscription")
async def get_subscription(bot_id: int, init_data: str) -> dict:
    bot_row = await _get_owned_bot(bot_id, init_data)
    return {
        "current_tariff": bot_row.tariff,
        "expires_at": bot_row.expires_at.isoformat() if bot_row.expires_at else None,
        "is_expired": bool(bot_row.expires_at and bot_row.expires_at < datetime.utcnow()),
        "options": [
            {"key": t.key, "title": t.title, "price": t.price, "duration_days": t.duration_days,
             "daily_limit": t.daily_limit}
            for t in TARIFFS.values() if not t.is_trial
        ],
    }


class RenewRequest(BaseModel):
    init_data: str
    tariff_key: str


@app.post("/api/bots/{bot_id}/subscription/renew")
async def renew_subscription(bot_id: int, payload: RenewRequest) -> dict:
    tariff = TARIFFS.get(payload.tariff_key)
    if tariff is None or tariff.is_trial:
        raise HTTPException(status_code=400, detail="Noto'g'ri tarif")

    tg_user = verify_telegram_webapp_data(payload.init_data)
    async with get_session() as session:
        result = await session.execute(select(BotModel).where(BotModel.id == bot_id))
        bot_row = result.scalar_one_or_none()
        if bot_row is None:
            raise HTTPException(status_code=404, detail="Bot topilmadi")

        owner_result = await session.execute(select(User).where(User.id == bot_row.owner_id))
        owner = owner_result.scalar_one()
        if owner.telegram_id != tg_user.get("id"):
            raise HTTPException(status_code=403, detail="Ruxsat yo'q")

        if owner.balance < tariff.price:
            raise HTTPException(status_code=402, detail="Balans yetarli emas")

        owner.balance -= tariff.price
        base_time = (
            bot_row.expires_at
            if bot_row.expires_at and bot_row.expires_at > datetime.utcnow()
            else datetime.utcnow()
        )
        bot_row.tariff = tariff.key
        bot_row.expires_at = base_time + timedelta(days=tariff.duration_days)
        await session.commit()
        new_expiry = bot_row.expires_at.isoformat()

    return {"ok": True, "new_expiry": new_expiry}


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

        ref_count_result = await session.execute(
            select(func.count()).select_from(Referral).where(Referral.referrer_id == user.id)
        )
        referral_count = ref_count_result.scalar_one()

    bot_username = platform_bot_username_cache.get("username", "")
    return {
        "telegram_id": user.telegram_id,
        "balance": user.balance,
        "referral_count": referral_count,
        "referral_link": f"https://t.me/{bot_username}?start={user.telegram_id}" if bot_username else None,
        "bots": [
            {"id": b.id, "username": b.bot_username, "type": b.bot_type,
             "status": b.status, "tariff": b.tariff,
             "expires_at": b.expires_at.isoformat() if b.expires_at else None}
            for b in bots
        ],
    }


@app.get("/api/catalog")
async def get_bot_catalog() -> dict:
    async with get_session() as session:
        catalog = await get_effective_catalog(session)
    return {
        "types": [
            {
                "key": info.key, "title": info.title, "emoji": info.emoji,
                "description": info.description, "price": info.price,
            }
            for info in catalog.values()
        ]
    }


class CreateBotRequest(BaseModel):
    init_data: str
    bot_type: str
    token: str


@app.post("/api/create-bot")
async def create_bot_via_miniapp(payload: CreateBotRequest) -> dict:
    async with get_session() as session:
        catalog = await get_effective_catalog(session)
    info = catalog.get(payload.bot_type)
    if info is None:
        raise HTTPException(status_code=400, detail="Noto'g'ri bot turi")
    if payload.bot_type not in BOT_TYPE_REGISTRY:
        raise HTTPException(status_code=400, detail="Bu bot turi hali ishlab chiqilmoqda")

    tg_user = verify_telegram_webapp_data(payload.init_data)

    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(f"https://api.telegram.org/bot{payload.token}/getMe")
        tg_check = resp.json()

    if not tg_check.get("ok"):
        raise HTTPException(status_code=400, detail="Token noto'g'ri yoki botga ulanib bo'lmadi")

    bot_username = tg_check["result"]["username"]
    bot_display_name = tg_check["result"]["first_name"]

    async with get_session() as session:
        user_result = await session.execute(select(User).where(User.telegram_id == tg_user["id"]))
        user = user_result.scalar_one_or_none()
        if user is None:
            raise HTTPException(status_code=404, detail="Foydalanuvchi topilmadi")

        if user.balance < info.price:
            raise HTTPException(status_code=402, detail="Balans yetarli emas")

        user.balance -= info.price
        new_bot = BotModel(
            owner_id=user.id,
            bot_type=info.key,
            status="active",
            bot_token=payload.token,
            bot_username=bot_username,
            display_name=bot_display_name,
            tariff="trial",
            expires_at=datetime.utcnow() + timedelta(days=3),
            settings_json=json.dumps({"owner_telegram_id": tg_user["id"]}),
        )
        session.add(new_bot)
        await session.flush()
        bot_id = new_bot.id
        await session.commit()

    webhook_url = f"{PUBLIC_BASE_URL}/webhook/{bot_id}"
    async with httpx.AsyncClient(timeout=10) as client:
        await client.get(
            f"https://api.telegram.org/bot{payload.token}/setWebhook",
            params={"url": webhook_url},
        )

    return {"ok": True, "bot_id": bot_id, "bot_username": bot_username}


@app.get("/api/bots/{bot_id}/kino/movies")
async def list_kino_movies(bot_id: int, init_data: str) -> dict:
    bot_row = await _get_owned_bot(bot_id, init_data)
    settings = json.loads(bot_row.settings_json or "{}")
    movies = settings.get("movies", {})
    return {
        "movies": [
            {"code": code, "added_at": data.get("added_at")}
            for code, data in sorted(movies.items(), key=lambda x: x[1].get("added_at", ""), reverse=True)
        ]
    }


class DeleteMovieRequest(BaseModel):
    init_data: str
    code: str


@app.post("/api/bots/{bot_id}/kino/delete-movie")
async def delete_kino_movie(bot_id: int, payload: DeleteMovieRequest) -> dict:
    await _get_owned_bot(bot_id, payload.init_data)
    async with get_session() as session:
        result = await session.execute(select(BotModel).where(BotModel.id == bot_id))
        fresh_row = result.scalar_one()
        settings = json.loads(fresh_row.settings_json or "{}")
        movies = settings.get("movies", {})
        movies.pop(payload.code, None)
        settings["movies"] = movies
        fresh_row.settings_json = json.dumps(settings)
        await session.commit()
    return {"ok": True}


@app.get("/api/bots/{bot_id}/anketa-export")
async def export_anketa(bot_id: int) -> StreamingResponse:
    """Anketa Bot javoblarini CSV holida eksport qiladi."""
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
    return {"status": "ok", "service": "Vezto API"}
