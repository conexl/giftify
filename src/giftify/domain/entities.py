from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
import re
from typing import Any

IDENTIFIER_RE = re.compile(
    r"^(?:[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}|\d+)$",
    re.IGNORECASE,
)


class Market(StrEnum):
    MRKT = "mrkt"
    PORTALS = "portals"
    TUNNEL = "tunnel"


@dataclass(frozen=True)
class Sale:
    market: Market
    sale_id: str
    occurred_at: str
    price_ton: float
    collection: str
    model: str
    symbol: str
    backdrop: str
    gift_number: float = 0
    model_rarity: float = 0
    symbol_rarity: float = 0
    backdrop_rarity: float = 0
    gift_link: str | None = None
    market_link: str | None = None


@dataclass(frozen=True)
class GiftListing:
    market: Market
    listing_id: str
    collection: str
    title: str
    current_price_ton: float
    model: str
    symbol: str
    backdrop: str
    market_link: str
    tg_link: str | None = None
    gift_number: float = 0
    model_rarity: float = 0
    symbol_rarity: float = 0
    backdrop_rarity: float = 0
    floor_gift_ton: float | None = None
    floor_model_ton: float | None = None
    photo_url: str | None = None
    raw: dict[str, Any] = field(default_factory=dict, repr=False, compare=False)

    @property
    def rule_key(self) -> tuple[str, str, str, str]:
        return (self.market.value, self.collection, self.model, self.backdrop)


@dataclass(frozen=True)
class GiftSnapshot:
    listing: GiftListing
    sales: list[Sale]


def number(value: Any) -> float:
    if value is None:
        return 0.0
    if isinstance(value, bool):
        return float(int(value))
    if isinstance(value, int | float):
        return float(value)
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return 0.0
        try:
            return float(stripped)
        except ValueError:
            return 0.0
    return 0.0


def nano_to_ton(value: Any) -> float:
    amount = number(value)
    if amount <= 0:
        return 0.0
    return amount / 1_000_000_000


def is_display_value(value: Any) -> bool:
    """Return whether a marketplace value is safe to show as a human label."""
    text = str(value or "").strip()
    return bool(text) and not IDENTIFIER_RE.fullmatch(text)


def display_value(value: Any, *, fallback: str = "") -> str:
    """Keep technical marketplace identifiers out of presentation fields."""
    return str(value).strip() if is_display_value(value) else fallback
