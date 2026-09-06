"""Child botlar uchun sinov muddati va tarif katalogi."""
from dataclasses import dataclass


@dataclass(frozen=True)
class TariffInfo:
    key: str
    title: str
    price: int  # so'mda, butun davr uchun
    duration_days: int
    daily_limit: int  # kuniga nechta xabar/so'rov
    is_trial: bool = False


TARIFFS: dict[str, TariffInfo] = {
    "trial": TariffInfo("trial", "🎁 Sinov (3 kun)", 0, 3, 500, is_trial=True),
    "weekly": TariffInfo("weekly", "📅 Haftalik", 19_000, 7, 2_000),
    "monthly": TariffInfo("monthly", "🗓 Oylik", 59_000, 30, 10_000),
    "yearly": TariffInfo("yearly", "🏆 Yillik (2 oy tekin)", 590_000, 365, 1_000_000),
}
