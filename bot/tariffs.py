"""Child botlar uchun oylik tariflar katalogi."""
from dataclasses import dataclass


@dataclass(frozen=True)
class TariffInfo:
    key: str
    title: str
    price_per_month: int  # so'mda
    daily_limit: int  # kuniga nechta xabar/so'rov


TARIFFS: dict[str, TariffInfo] = {
    "free": TariffInfo("free", "🆓 Free", 0, 100),
    "start": TariffInfo("start", "🚀 Start", 29_000, 1_000),
    "pro": TariffInfo("pro", "💎 Pro", 79_000, 10_000),
    "vip": TariffInfo("vip", "👑 VIP", 199_000, 1_000_000),
}
