from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Protocol

import httpx

from giftify.domain import GiftListing, Market
from giftify.rules import AutoBuyRule


class PurchaseStatus(StrEnum):
    DRY_RUN = "dry_run"
    SUCCESS = "success"
    PRICE_CHANGED = "price_changed"
    ALREADY_SOLD = "already_sold"
    INSUFFICIENT_BALANCE = "insufficient_balance"
    RATE_LIMITED = "rate_limited"
    AUTH_FAILED = "auth_failed"
    FAILED = "failed"


@dataclass(frozen=True)
class PurchaseResult:
    status: PurchaseStatus
    message: str
    external_purchase_id: str | None = None


class PurchaseExecutor(Protocol):
    async def buy(self, rule: AutoBuyRule, listing: GiftListing, *, idempotency_key: str) -> PurchaseResult:
        ...


class DryRunPurchaseExecutor:
    async def buy(self, rule: AutoBuyRule, listing: GiftListing, *, idempotency_key: str) -> PurchaseResult:
        return PurchaseResult(
            status=PurchaseStatus.DRY_RUN,
            message=(
                f"Would buy {listing.market.value}/{listing.listing_id} "
                f"for {listing.current_price_ton:.3f} TON by rule {rule.id}"
            ),
            external_purchase_id=idempotency_key,
        )


class HttpPurchaseExecutor:
    def __init__(self, route_url: str, *, timeout_seconds: float = 20.0, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self._route_url = route_url
        self._timeout_seconds = timeout_seconds
        self._transport = transport

    async def buy(self, rule: AutoBuyRule, listing: GiftListing, *, idempotency_key: str) -> PurchaseResult:
        if listing.current_price_ton > rule.max_price_ton:
            return PurchaseResult(PurchaseStatus.PRICE_CHANGED, "listing price is above rule maximum")

        payload = {
            "idempotency_key": idempotency_key,
            "market": listing.market.value,
            "listing_id": listing.listing_id,
            "expected_price_ton": listing.current_price_ton,
            "rule_id": rule.id,
            "user_id": rule.user_id,
        }
        async with httpx.AsyncClient(timeout=self._timeout_seconds, transport=self._transport) as client:
            response = await client.post(self._route_url, json=payload)

        if response.status_code == 409:
            return PurchaseResult(PurchaseStatus.ALREADY_SOLD, response.text or "already sold")
        if response.status_code == 429:
            return PurchaseResult(PurchaseStatus.RATE_LIMITED, response.text or "rate limited")
        if response.status_code in {401, 403}:
            return PurchaseResult(PurchaseStatus.AUTH_FAILED, response.text or "auth failed")
        if response.status_code >= 500:
            return PurchaseResult(PurchaseStatus.FAILED, response.text or "purchase route failed")

        response.raise_for_status()
        data = response.json() if response.content else {}
        status = PurchaseStatus(data.get("status", PurchaseStatus.SUCCESS.value))
        return PurchaseResult(
            status=status,
            message=str(data.get("message") or status.value),
            external_purchase_id=data.get("purchase_id"),
        )


class MarketplacePurchaseRouter:
    """Routes purchase requests to market-specific purchase executors based on listing.market."""

    def __init__(
        self,
        executors: dict[Market, PurchaseExecutor],
        *,
        default_executor: PurchaseExecutor | None = None,
    ) -> None:
        self._executors = executors
        self._default_executor = default_executor or DryRunPurchaseExecutor()

    async def buy(self, rule: AutoBuyRule, listing: GiftListing, *, idempotency_key: str) -> PurchaseResult:
        executor = self._executors.get(listing.market, self._default_executor)
        return await executor.buy(rule, listing, idempotency_key=idempotency_key)


def _json_object(response: httpx.Response) -> dict[str, Any]:
    """Normalize MRKT's single-item object and batch-list response formats."""
    try:
        payload = response.json()
    except (ValueError, TypeError):
        return {}

    return _response_object(payload)


def _response_object(payload: Any) -> dict[str, Any]:
    if isinstance(payload, dict):
        for key in ("data", "results", "gifts"):
            nested = payload.get(key)
            if isinstance(nested, list) and nested and isinstance(nested[0], dict):
                return nested[0]
        return payload
    if isinstance(payload, list) and payload and isinstance(payload[0], dict):
        return payload[0]
    return {}


def _first_value(data: dict[str, Any], *keys: str) -> Any | None:
    return next((data[key] for key in keys if data.get(key) is not None), None)


def _mrkt_result_status(data: dict[str, Any]) -> tuple[PurchaseStatus, str]:
    message = str(_first_value(data, "message", "error", "detail") or "purchase successful")
    marker = " ".join(
        str(value).lower()
        for value in (_first_value(data, "status", "code", "error"), message)
        if value is not None
    )

    if any(value in marker for value in ("insufficient", "not_enough_funds", "not enough funds")):
        return PurchaseStatus.INSUFFICIENT_BALANCE, message
    if any(value in marker for value in ("already sold", "not found", "sold_out", "sold out")):
        return PurchaseStatus.ALREADY_SOLD, message
    if any(value in marker for value in ("price_changed", "price changed", "price mismatch")):
        return PurchaseStatus.PRICE_CHANGED, message
    if "rate" in marker and "limit" in marker:
        return PurchaseStatus.RATE_LIMITED, message
    if any(value in marker for value in ("unauthorized", "auth", "token")):
        return PurchaseStatus.AUTH_FAILED, message
    if data.get("error") or any(value in marker for value in ("failed", "rejected", "error")):
        return PurchaseStatus.FAILED, message
    return PurchaseStatus.SUCCESS, message


def _portals_result_status(data: dict[str, Any], message: str) -> tuple[PurchaseStatus, str]:
    marker = message.lower()
    if any(v in marker for v in ("insufficient", "balance", "not_enough_funds")):
        return PurchaseStatus.INSUFFICIENT_BALANCE, message
    if any(v in marker for v in ("already sold", "not found", "sold", "unavailable")):
        return PurchaseStatus.ALREADY_SOLD, message
    if any(v in marker for v in ("price", "changed", "mismatch")):
        return PurchaseStatus.PRICE_CHANGED, message
    if "rate" in marker and "limit" in marker:
        return PurchaseStatus.RATE_LIMITED, message
    if any(v in marker for v in ("unauthorized", "auth", "token")):
        return PurchaseStatus.AUTH_FAILED, message
    if data.get("error") or "failed" in marker:
        return PurchaseStatus.FAILED, message
    return PurchaseStatus.SUCCESS, message


def _tunnel_result_status(data: dict[str, Any], message: str) -> tuple[PurchaseStatus, str]:
    marker = message.lower()
    if any(v in marker for v in ("insufficient", "balance", "not_enough_funds", "not enough funds", "not enough ton")):
        return PurchaseStatus.INSUFFICIENT_BALANCE, message
    if any(v in marker for v in ("already sold", "not found", "sold", "unavailable", "gift already sold", "gift not found")):
        return PurchaseStatus.ALREADY_SOLD, message
    if any(v in marker for v in ("price", "changed", "mismatch")):
        return PurchaseStatus.PRICE_CHANGED, message
    if "rate" in marker and "limit" in marker:
        return PurchaseStatus.RATE_LIMITED, message
    if any(v in marker for v in ("unauthorized", "auth", "token", "invalid auth data")):
        return PurchaseStatus.AUTH_FAILED, message
    if data.get("status") == "error" or data.get("error") or "failed" in marker:
        return PurchaseStatus.FAILED, message
    return PurchaseStatus.SUCCESS, message
