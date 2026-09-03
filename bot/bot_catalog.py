"""Bot turlari katalogi — narx va tavsiflar screenshotlardagi qiymatlar asosida."""
from dataclasses import dataclass


@dataclass(frozen=True)
class BotTypeInfo:
    key: str
    title: str
    emoji: str
    description: str
    price: int  # so'mda, bir martalik yaratish narxi
    demo_username: str | None = None


BOT_CATALOG: dict[str, BotTypeInfo] = {
    "kino": BotTypeInfo(
        key="kino", title="Kino Bot", emoji="🎬", price=9_000,
        description=(
            "Ushbu tizim orqali siz kinolarni botga yuklaysiz va ularga maxsus "
            "kod biriktirasiz. Foydalanuvchilar shu kodni yuborib kinoni oladi."
        ),
    ),
    "pul": BotTypeInfo(
        key="pul", title="Pul Bot", emoji="💰", price=9_000,
        description=(
            "Ushbu bot orqali foydalanuvchilar referal havola orqali yangi "
            "odamlarni taklif qilib, pul ishlashlari mumkin."
        ),
    ),
    "openbudget": BotTypeInfo(
        key="openbudget", title="OpenBudget Bot", emoji="📦", price=15_000,
        description="Ushbu bot Open Budget loyihalari uchun ovoz (vote) yig'ish uchun mo'ljallangan.",
    ),
    "nakrutka": BotTypeInfo(
        key="nakrutka", title="Nakrutka Bot", emoji="🚀", price=15_000,
        description="Ushbu bot orqali siz SMM xizmatlarini qulay interfeys orqali sotishingiz mumkin.",
    ),
    "vipkanal": BotTypeInfo(
        key="vipkanal", title="VipKanal Bot", emoji="🔐", price=15_000,
        description=(
            "Ushbu bot orqali siz VIP kanal yoki guruhlarga pullik obunalarni "
            "sotishingiz va foydalanuvchilarni avtomatik boshqarishingiz mumkin."
        ),
    ),
    "aloqa": BotTypeInfo(
        key="aloqa", title="Aloqa Bot", emoji="📞", price=15_000,
        description="Ushbu aloqa boti orqali siz foydalanuvchilardan murojaatlar qabul qilishingiz mumkin.",
        demo_username="SafoHelpBot",
    ),
    "taxi": BotTypeInfo(
        key="taxi", title="Taxi Bot", emoji="🚕", price=15_000,
        description="Ushbu tizim orqali foydalanuvchilar bot orqali tez va oson taxi yoki pochta buyurtma berishlari mumkin.",
        demo_username="DemoTaxi1_Bot",
    ),
    "anketa": BotTypeInfo(
        key="anketa", title="Anketa Bot", emoji="📝", price=15_000,
        description="Ushbu tizim orqali siz istalgan miqdorda savollar yaratasiz va foydalanuvchilardan ketma-ket javob olasiz.",
        demo_username="DemoAnketaBot",
    ),
    "kafe_pos": BotTypeInfo(
        key="kafe_pos", title="Kafe POS Bot", emoji="🍽", price=150_000,
        description=(
            "Bu mijoz buyurtma beradigan bot EMAS. Bu — kafe va restoran "
            "XODIMLARI uchun ichki boshqaruv tizimi."
        ),
    ),
    "konkurs": BotTypeInfo(
        key="konkurs", title="Konkurs Bot", emoji="🏆", price=7_000,
        description="Referal asosidagi konkurs boti. Siz sovrinlarni belgilaysiz, ishtirokchilar taklif havolasi orqali qatnashadi.",
        demo_username="DemoKonkursBot",
    ),
}
