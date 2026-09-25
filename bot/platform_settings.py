"""
Butun platformaga tegishli sozlamalar (karta raqami, majburiy obuna,
bot narxlari, admin qo'shgan yangi bot turlari). Bular kalit-qiymat
jadvalida (PlatformSetting) saqlanadi — shu tufayli admin panel orqali
o'zgartirilganda serverni qayta deploy qilish shart emas.
"""
import json

from sqlalchemy import select

from bot.bot_catalog import BOT_CATALOG, BotTypeInfo
from database.models import PlatformSetting


async def get_setting(session, key: str, default: str = "") -> str:
    result = await session.execute(select(PlatformSetting).where(PlatformSetting.key == key))
    row = result.scalar_one_or_none()
    return row.value if row else default


async def set_setting(session, key: str, value: str) -> None:
    result = await session.execute(select(PlatformSetting).where(PlatformSetting.key == key))
    row = result.scalar_one_or_none()
    if row is None:
        session.add(PlatformSetting(key=key, value=value))
    else:
        row.value = value
    await session.commit()


async def delete_setting(session, key: str) -> None:
    result = await session.execute(select(PlatformSetting).where(PlatformSetting.key == key))
    row = result.scalar_one_or_none()
    if row is not None:
        await session.delete(row)
        await session.commit()


async def get_effective_catalog(session) -> dict[str, BotTypeInfo]:
    """
    Asosiy (kodga yozilgan) katalogga admin panel orqali kiritilgan
    narx o'zgarishlari, yashirilgan turlar va yangi (metadata) turlarni
    birlashtirib qaytaradi.
    """
    catalog = dict(BOT_CATALOG)

    overrides = json.loads(await get_setting(session, "price_overrides", "{}"))
    for key, price in overrides.items():
        if key in catalog:
            base = catalog[key]
            catalog[key] = BotTypeInfo(
                base.key, base.title, base.emoji, base.description,
                int(price), base.demo_username,
            )

    hidden = json.loads(await get_setting(session, "hidden_types", "[]"))
    for key in hidden:
        catalog.pop(key, None)

    custom_types = json.loads(await get_setting(session, "custom_bot_types", "[]"))
    for c in custom_types:
        catalog[c["key"]] = BotTypeInfo(
            c["key"], c["title"], c["emoji"], c["description"], int(c["price"]),
        )

    return catalog
