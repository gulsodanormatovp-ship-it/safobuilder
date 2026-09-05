"""
Bot turi -> mantiq klassi ro'yxati. Barcha 10 turdagi bot shu yerda ro'yxatdan
o'tgan — yangi tur qo'shish uchun shunchaki bitta qator qo'shish kifoya.
"""
from .aloqa_bot import AloqaBot
from .anketa_bot import AnketaBot
from .base import ChildBot
from .kafe_pos_bot import KafePosBot
from .kino_bot import KinoBot
from .konkurs_bot import KonkursBot
from .nakrutka_bot import NakrutkaBot
from .openbudget_bot import OpenBudgetBot
from .pul_bot import PulBot
from .taxi_bot import TaxiBot
from .vipkanal_bot import VipKanalBot

BOT_TYPE_REGISTRY: dict[str, type[ChildBot]] = {
    "kino": KinoBot,
    "taxi": TaxiBot,
    "anketa": AnketaBot,
    "pul": PulBot,
    "openbudget": OpenBudgetBot,
    "vipkanal": VipKanalBot,
    "aloqa": AloqaBot,
    "kafe_pos": KafePosBot,
    "nakrutka": NakrutkaBot,
    "konkurs": KonkursBot,
}
