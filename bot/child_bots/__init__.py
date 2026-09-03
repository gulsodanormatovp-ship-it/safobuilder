"""
Bot turi -> mantiq klassi ro'yxati. Yangi bot turi qo'shganda faqat shu
lug'atga bitta qator qo'shasiz — qolgan tizim (runtime router, API) hech
narsa o'zgartirmasdan yangi turni qabul qiladi.
"""
from .anketa_bot import AnketaBot
from .base import ChildBot
from .kino_bot import KinoBot
from .taxi_bot import TaxiBot

# TODO: quyidagilarni README dagi "Yangi bot turi qo'shish" bo'limiga
# muvofiq amalga oshiring — struktura tayyor, mantiqni yozish qoladi:
#   pul_bot.py, openbudget_bot.py, vipkanal_bot.py, aloqa_bot.py,
#   kafe_pos_bot.py, nakrutka_bot.py, konkurs_bot.py

BOT_TYPE_REGISTRY: dict[str, type[ChildBot]] = {
    "kino": KinoBot,
    "taxi": TaxiBot,
    "anketa": AnketaBot,
}
