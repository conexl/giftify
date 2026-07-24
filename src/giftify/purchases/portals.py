from __future__ import annotations

from decimal import Decimal
import httpx

from giftify.clients import TokenProvider
from giftify.domain import GiftListing, Market
from giftify.proxies import ProxyPool
from giftify.rules import AutoBuyRule
from .base import PurchaseResult, PurchaseStatus, _portals_result_status


class PortalsPurchaseExecutor:
    """Direct purchase executor for Portals marketplace."""

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
        if listing.market != Market.PORTALS:
            return PurchaseResult(
                PurchaseStatus.FAILED,
                f"PortalsPurchaseExecutor only supports PORTALS market, got {listing.market.value}",
            )

        if listing.current_price_ton > rule.max_price_ton:
            return PurchaseResult(PurchaseStatus.PRICE_CHANGED, "listing price is above rule maximum")

        token = await self._token_provider.get_token()
        if not token:
            return PurchaseResult(PurchaseStatus.AUTH_FAILED, "no token available")

        price_str = str(Decimal(str(listing.current_price_ton)))
        auth_header = token if token.startswith(("tma ", "Bearer ", "bearer ")) else f"tma {token}"

        headers = {
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64; rv:152.0) Gecko/20100101 Firefox/152.0",
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "en-US,en;q=0.9",
            "Content-Type": "application/json",
            "Authorization": auth_header,
            "Origin": "https://portal-market.com",
            "Referer": "https://portal-market.com/",
            "x-request-id": idempotency_key,
        }

        payload = {
            "nft_details": [
                {
                    "id": listing.listing_id,
                    "price": price_str,
                }
            ]
        }

        request_proxy = await self._next_proxy()
        try:
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(self._timeout_seconds, connect=4.0),
                proxy=request_proxy,
                transport=self._transport,
            ) as client:
                response = await client.post(
                    f"{self._base_url}/api/nfts",
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
            auth_header = token if token.startswith(("tma ", "Bearer ", "bearer ")) else f"tma {token}"
            headers["Authorization"] = auth_header
            request_proxy = await self._next_proxy()
            try:
                async with httpx.AsyncClient(
                    timeout=httpx.Timeout(self._timeout_seconds, connect=4.0),
                    proxy=request_proxy,
                    transport=self._transport,
                ) as client:
                    response = await client.post(
                        f"{self._base_url}/api/nfts",
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
        if response.status_code in {404, 409}:
            return PurchaseResult(PurchaseStatus.ALREADY_SOLD, response.text or "already sold")
        if response.status_code == 422:
            return PurchaseResult(PurchaseStatus.PRICE_CHANGED, response.text or "price changed")
        if response.status_code >= 500:
            return PurchaseResult(PurchaseStatus.FAILED, response.text or "server error")

        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            return PurchaseResult(PurchaseStatus.FAILED, f"HTTP {exc.response.status_code}: {exc.response.text}")

        try:
            res_data = response.json()
        except (ValueError, TypeError):
            res_data = None

        if isinstance(res_data, dict):
            details = res_data.get("nft_details")
            if isinstance(details, list) and details:
                item = details[0]
                item_id = item.get("id") or listing.listing_id
                return PurchaseResult(
                    status=PurchaseStatus.SUCCESS,
                    message="Portals purchase successful",
                    external_purchase_id=str(item_id),
                )
            if "error" in res_data or "message" in res_data:
                msg = str(res_data.get("message") or res_data.get("error"))
                status, msg = _portals_result_status(res_data, msg)
                return PurchaseResult(status=status, message=msg)

        return PurchaseResult(
            status=PurchaseStatus.SUCCESS,
            message="Portals purchase submitted",
            external_purchase_id=listing.listing_id,
        )

    async def _next_proxy(self) -> str | None:
        return await self._proxy_pool.next() if self._proxy_pool is not None else self._proxy

    async def _mark_proxy_failed(self, proxy: str | None) -> None:
        if self._proxy_pool is not None:
            await self._proxy_pool.mark_failed(proxy)

    async def _mark_proxy_success(self, proxy: str | None) -> None:
        if self._proxy_pool is not None:
            await self._proxy_pool.mark_success(proxy)
