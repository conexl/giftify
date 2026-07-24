from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
import httpx

from giftify.clients import TokenProvider
from giftify.domain import GiftListing, Market
from giftify.proxies import ProxyPool
from giftify.rules import AutoBuyRule
from .base import (
    PurchaseResult,
    PurchaseStatus,
    _first_value,
    _json_object,
    _mrkt_result_status,
    _response_object,
)


class MrktPurchaseExecutor:
    """Direct purchase executor for MRKT marketplace."""

    def __init__(
        self,
        base_url: str,
        token_provider: TokenProvider,
        *,
        proxy: str | None = None,
        proxy_pool: ProxyPool | None = None,
        timeout_seconds: float = 20.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._token_provider = token_provider
        self._proxy = proxy
        self._proxy_pool = proxy_pool
        self._timeout_seconds = timeout_seconds
        self._transport = transport

    async def buy(self, rule: AutoBuyRule, listing: GiftListing, *, idempotency_key: str) -> PurchaseResult:
        if listing.market != Market.MRKT:
            return PurchaseResult(
                PurchaseStatus.FAILED,
                f"MrktPurchaseExecutor only supports MRKT market, got {listing.market.value}",
            )

        if listing.current_price_ton > rule.max_price_ton:
            return PurchaseResult(PurchaseStatus.PRICE_CHANGED, "listing price is above rule maximum")

        token = await self._token_provider.get_token()
        if not token:
            return PurchaseResult(PurchaseStatus.AUTH_FAILED, "no token available")

        price_nano = int(
            (Decimal(str(listing.current_price_ton)) * Decimal("1000000000")).to_integral_value(
                rounding=ROUND_HALF_UP
            )
        )

        headers = {
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64; rv:152.0) Gecko/20100101 Firefox/152.0",
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "en-US,en;q=0.9",
            "Content-Type": "application/json",
            "Authorization": token,
            "Origin": "https://cdn.tgmrkt.io",
            "Referer": "https://cdn.tgmrkt.io/",
            "Cookie": f"access_token={token}",
            "Idempotency-Key": idempotency_key,
        }

        payload = {
            "ids": [listing.listing_id],
            "prices": {listing.listing_id: price_nano},
        }

        request_proxy = await self._next_proxy()
        try:
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(self._timeout_seconds, connect=4.0),
                proxy=request_proxy,
                transport=self._transport,
            ) as client:
                response = await client.post(
                    f"{self._base_url}/api/v1/gifts/buy",
                    headers=headers,
                    json=payload,
                )
        except httpx.TransportError as exc:
            await self._mark_proxy_failed(request_proxy)
            return PurchaseResult(PurchaseStatus.FAILED, f"transport error: {exc}")

        if response.status_code == 401:
            token = await self._token_provider.refresh_token()
            if not token:
                return PurchaseResult(PurchaseStatus.AUTH_FAILED, "token refresh failed")
            headers["Authorization"] = token
            headers["Cookie"] = f"access_token={token}"
            request_proxy = await self._next_proxy()
            try:
                async with httpx.AsyncClient(
                    timeout=httpx.Timeout(self._timeout_seconds, connect=4.0),
                    proxy=request_proxy,
                    transport=self._transport,
                ) as client:
                    response = await client.post(
                        f"{self._base_url}/api/v1/gifts/buy",
                        headers=headers,
                        json=payload,
                    )
            except httpx.TransportError as exc:
                await self._mark_proxy_failed(request_proxy)
                return PurchaseResult(PurchaseStatus.FAILED, f"transport error after refresh: {exc}")

        await self._mark_proxy_success(request_proxy)

        if response.status_code == 429:
            return PurchaseResult(PurchaseStatus.RATE_LIMITED, response.text or "rate limited")
        if response.status_code in {401, 403}:
            return PurchaseResult(PurchaseStatus.AUTH_FAILED, response.text or "auth failed")
        if response.status_code == 409:
            return PurchaseResult(PurchaseStatus.ALREADY_SOLD, response.text or "already sold")
        if response.status_code == 422:
            data = _json_object(response)
            msg = data.get("message") or data.get("error") or response.text or "price changed or validation error"
            return PurchaseResult(PurchaseStatus.PRICE_CHANGED, msg)
        if response.status_code >= 500:
            return PurchaseResult(PurchaseStatus.FAILED, response.text or "server error")

        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            return PurchaseResult(PurchaseStatus.FAILED, f"HTTP {exc.response.status_code}: {exc.response.text}")

        try:
            payload = response.json()
        except (ValueError, TypeError):
            payload = None
        if payload == []:
            return PurchaseResult(
                PurchaseStatus.PRICE_CHANGED,
                "MRKT did not confirm this listing at the submitted price",
            )
        data = _response_object(payload)
        if not data:
            return PurchaseResult(PurchaseStatus.FAILED, "unexpected empty response from MRKT")

        status, message = _mrkt_result_status(data)
        purchase_id = _first_value(data, "purchase_id", "id", "order_id")
        user_gift = data.get("userGift")
        if purchase_id is None and isinstance(user_gift, dict):
            purchase_id = user_gift.get("id")
        if message == "purchase successful" and isinstance(user_gift, dict):
            message = str(user_gift.get("name") or user_gift.get("title") or message)

        return PurchaseResult(
            status=status,
            message=message,
            external_purchase_id=str(purchase_id) if purchase_id is not None else None,
        )

    async def _next_proxy(self) -> str | None:
        return await self._proxy_pool.next() if self._proxy_pool is not None else self._proxy

    async def _mark_proxy_failed(self, proxy: str | None) -> None:
        if self._proxy_pool is not None:
            await self._proxy_pool.mark_failed(proxy)

    async def _mark_proxy_success(self, proxy: str | None) -> None:
        if self._proxy_pool is not None:
            await self._proxy_pool.mark_success(proxy)
