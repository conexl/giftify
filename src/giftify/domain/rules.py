from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from .entities import GiftListing, Market


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class AutoBuyRule:
    id: int
    user_id: int
    collection: str
    max_price_ton: float
    market: Market | None = None
    model: str | None = None
    backdrop: str | None = None
    enabled: bool = True
    max_spend_ton: float | None = None
    spent_ton: float = 0
    created_at: str = ""
    updated_at: str = ""

    def matches(self, listing: GiftListing) -> bool:
        if not self.enabled:
            return False
        if self.max_spend_ton is not None and self.spent_ton + listing.current_price_ton > self.max_spend_ton:
            return False
        if self.market is not None and listing.market != self.market:
            return False
        if _norm(self.collection) != _norm(listing.collection) and _norm(self.collection) != _norm(listing.title):
            return False
        if self.model and _norm(self.model) != _norm(listing.model):
            return False
        if self.backdrop and _norm(self.backdrop) != _norm(listing.backdrop):
            return False
        return listing.current_price_ton <= self.max_price_ton


@dataclass(frozen=True)
class NewRule:
    user_id: int
    collection: str
    max_price_ton: float
    market: Market | None = None
    model: str | None = None
    backdrop: str | None = None
    enabled: bool = True
    max_spend_ton: float | None = None

    def validate(self) -> None:
        if self.user_id <= 0:
            raise ValueError("user_id must be positive")
        if not self.collection.strip():
            raise ValueError("collection is required")
        if self.max_price_ton <= 0:
            raise ValueError("max_price_ton must be positive")
        if self.max_spend_ton is not None and self.max_spend_ton <= 0:
            raise ValueError("max_spend_ton must be positive")


@dataclass(frozen=True)
class Match:
    rule: AutoBuyRule
    listing: GiftListing

    @property
    def idempotency_key(self) -> str:
        return f"{self.rule.id}:{self.listing.market.value}:{self.listing.listing_id}"


class RuleMatcher:
    def match(self, rules: list[AutoBuyRule], listings: list[GiftListing]) -> list[Match]:
        matches: list[Match] = []
        for listing in listings:
            for rule in rules:
                if rule.matches(listing):
                    matches.append(Match(rule=rule, listing=listing))
        return matches


def _norm(value: str | None) -> str:
    return (value or "").replace("’", "'").replace("‘", "'").strip().casefold()
