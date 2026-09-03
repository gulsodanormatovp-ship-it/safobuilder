"""
SafoBuilder platformasi uchun ma'lumotlar bazasi modellari.

Asosiy g'oya: bitta jismoniy server minglab "child bot"larni boshqarishi mumkin,
chunki har bir child bot faqat DB'dagi bitta qator (Bot jadvali) — alohida process
yoki fayl talab qilmaydi. Runtime router shu jadvaldan bot_id bo'yicha turi va
sozlamalarini o'qib, mos handlerga uzatadi.
"""
from __future__ import annotations

import enum
from datetime import datetime

from sqlalchemy import (
    BigInteger, Boolean, DateTime, Enum, ForeignKey, Integer,
    Numeric, String, Text, UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class BotType(str, enum.Enum):
    KINO = "kino"
    PUL = "pul"
    OPENBUDGET = "openbudget"
    NAKRUTKA = "nakrutka"
    VIPKANAL = "vipkanal"
    ALOQA = "aloqa"
    TAXI = "taxi"
    ANKETA = "anketa"
    KAFE_POS = "kafe_pos"
    KONKURS = "konkurs"


class BotStatus(str, enum.Enum):
    ACTIVE = "active"
    PAUSED = "paused"
    DELETED = "deleted"


class PaymentStatus(str, enum.Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class PaymentMethod(str, enum.Enum):
    CLICK = "click"
    PAYME = "payme"
    PAYNET = "paynet"
    CARD_MANUAL = "card_manual"


class User(Base):
    """Platformadan foydalanuvchi (bot egasi)."""
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True)
    username: Mapped[str | None] = mapped_column(String(64), nullable=True)
    full_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    balance: Mapped[int] = mapped_column(Integer, default=0)  # so'mda
    referred_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    bots: Mapped[list["Bot"]] = relationship(back_populates="owner")
    payments: Mapped[list["Payment"]] = relationship(back_populates="user")


class Bot(Base):
    """Foydalanuvchi yaratgan har bitta child bot."""
    __tablename__ = "bots"
    __table_args__ = (UniqueConstraint("bot_token", name="uq_bot_token"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    bot_type: Mapped[BotType] = mapped_column(Enum(BotType))
    status: Mapped[BotStatus] = mapped_column(Enum(BotStatus), default=BotStatus.ACTIVE)

    bot_token: Mapped[str] = mapped_column(String(128))
    bot_username: Mapped[str] = mapped_column(String(64))
    display_name: Mapped[str] = mapped_column(String(128))

    # Har bir bot turiga xos sozlamalar shu yerda JSON-matn sifatida saqlanadi
    # (masalan Kino Bot uchun {"movie_channel_id": -100123}, Taxi uchun
    # {"driver_group_id": -100456}) — shu tufayli sxema o'zgarmasdan yangi
    # sozlamalar qo'shish mumkin.
    settings_json: Mapped[str] = mapped_column(Text, default="{}")

    tariff: Mapped[str] = mapped_column(String(32), default="free")
    expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    owner: Mapped["User"] = relationship(back_populates="bots")
    stats: Mapped[list["BotStat"]] = relationship(back_populates="bot")


class BotStat(Base):
    """Kunlik statistika — Mini App dashboardidagi grafik shu yerdan o'qiladi."""
    __tablename__ = "bot_stats"

    id: Mapped[int] = mapped_column(primary_key=True)
    bot_id: Mapped[int] = mapped_column(ForeignKey("bots.id"), index=True)
    date: Mapped[datetime] = mapped_column(DateTime, index=True)
    new_users: Mapped[int] = mapped_column(Integer, default=0)
    messages: Mapped[int] = mapped_column(Integer, default=0)
    requests: Mapped[int] = mapped_column(Integer, default=0)
    errors: Mapped[int] = mapped_column(Integer, default=0)
    undelivered: Mapped[int] = mapped_column(Integer, default=0)

    bot: Mapped["Bot"] = relationship(back_populates="stats")


class Payment(Base):
    """
    To'lov so'rovi. CLICK/PAYME/PAYNET — avtomatik (webhook orqali status
    yangilanadi). CARD_MANUAL — foydalanuvchi chek yuboradi, admin
    tasdiqlagach `status=APPROVED` bo'lib, balans avtomatik oshadi.
    """
    __tablename__ = "payments"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    amount: Mapped[int] = mapped_column(Integer)  # so'mda
    method: Mapped[PaymentMethod] = mapped_column(Enum(PaymentMethod))
    status: Mapped[PaymentStatus] = mapped_column(Enum(PaymentStatus), default=PaymentStatus.PENDING)

    receipt_file_id: Mapped[str | None] = mapped_column(String(256), nullable=True)
    admin_comment: Mapped[str | None] = mapped_column(String(256), nullable=True)
    reviewed_by: Mapped[int | None] = mapped_column(BigInteger, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    user: Mapped["User"] = relationship(back_populates="payments")


class Referral(Base):
    """Referal orqali bog'langan foydalanuvchilar va bonuslar."""
    __tablename__ = "referrals"

    id: Mapped[int] = mapped_column(primary_key=True)
    referrer_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    referred_id: Mapped[int] = mapped_column(ForeignKey("users.id"), unique=True)
    bonus_amount: Mapped[int] = mapped_column(Integer, default=500)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
