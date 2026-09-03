import asyncio
import logging
import os

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from dotenv import load_dotenv

from bot.handlers import create_bot, my_bots, payment, profile, start
from database.db import init_db

load_dotenv()
logging.basicConfig(level=logging.INFO)


async def main() -> None:
    token = os.environ["PLATFORM_BOT_TOKEN"]
    bot = Bot(token=token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher(storage=MemoryStorage())

    dp.include_router(start.router)
    dp.include_router(create_bot.router)
    dp.include_router(my_bots.router)
    dp.include_router(payment.router)
    dp.include_router(profile.router)

    await init_db()
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
