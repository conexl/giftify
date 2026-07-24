from __future__ import annotations

import time
from typing import Any
import httpx

from giftify.clients import TokenProvider
from giftify.domain import GiftListing, Market
from giftify.proxies import ProxyPool
from giftify.rules import AutoBuyRule
from .base import PurchaseResult, PurchaseStatus, _tunnel_result_status


class TunnelPurchaseExecutor:
    """Direct purchase executor for Tunnel marketplace."""

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
        if listing.market != Market.TUNNEL:
            return PurchaseResult(
                PurchaseStatus.FAILED,
                f"TunnelPurchaseExecutor only supports TUNNEL market, got {listing.market.value}",
            )

        if listing.current_price_ton > rule.max_price_ton:
            return PurchaseResult(PurchaseStatus.PRICE_CHANGED, "listing price is above rule maximum")

        token = await self._token_provider.get_token()
        if not token:
            return PurchaseResult(PurchaseStatus.AUTH_FAILED, "no token available")

        headers = {
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64; rv:152.0) Gecko/20100101 Firefox/152.0",
            "Accept": "*/*",
            "Accept-Language": "en-US,en;q=0.9",
            "Content-Type": "application/json",
            "Origin": "https://marketplace.tonnel.network",
            "Referer": "https://marketplace.tonnel.network/",
        }

        ts = int(time.time())
        payload = {
            "authData": token,
            "asset": "TON",
            "price": listing.current_price_ton,
            "timestamp": ts,
            "wtf": self._encrypt_wtf(ts),
        }

        url = f"{self._base_url}/api/buyGift/{listing.listing_id}"
        request_proxy = await self._next_proxy()
        try:
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(self._timeout_seconds, connect=4.0),
                proxy=request_proxy,
                transport=self._transport,
            ) as client:
                response = await client.post(url, headers=headers, json=payload)
        except httpx.TransportError as exc:
            await self._mark_proxy_failed(request_proxy)
            return PurchaseResult(PurchaseStatus.FAILED, f"transport error: {exc}")

        if response.status_code == 401:
            token = await self._token_provider.refresh_token()
            if not token:
                return PurchaseResult(PurchaseStatus.AUTH_FAILED, "token refresh failed")
            payload["authData"] = token
            request_proxy = await self._next_proxy()
            try:
                async with httpx.AsyncClient(
                    timeout=httpx.Timeout(self._timeout_seconds, connect=4.0),
                    proxy=request_proxy,
                    transport=self._transport,
                ) as client:
                    response = await client.post(url, headers=headers, json=payload)
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
            status_val = str(res_data.get("status") or "").lower()
            msg = str(res_data.get("message") or res_data.get("error") or status_val or "purchase submitted")
            if status_val == "error" or "error" in res_data:
                status, msg = _tunnel_result_status(res_data, msg)
                return PurchaseResult(status=status, message=msg)
            if status_val == "success" or res_data.get("success") is True or "tx" in res_data:
                tx_id = str(res_data.get("tx") or res_data.get("purchase_id") or listing.listing_id)
                return PurchaseResult(
                    status=PurchaseStatus.SUCCESS,
                    message="Tunnel purchase successful",
                    external_purchase_id=tx_id,
                )

        return PurchaseResult(
            status=PurchaseStatus.SUCCESS,
            message="Tunnel purchase submitted",
            external_purchase_id=listing.listing_id,
        )

    @staticmethod
    def _encrypt_wtf(timestamp: int, secret_key: str = "yowtfisthispieceofshitiiit") -> str:
        import base64
        import os
        from hashlib import md5
        try:
            from Crypto.Cipher import AES
        except ImportError:
            from Cryptodome.Cipher import AES

        plaintext = str(timestamp).encode("utf-8")
        pad_len = 16 - (len(plaintext) % 16)
        plaintext += bytes([pad_len]) * pad_len

        salt = os.urandom(8)
        d = d_i = b""
        password = secret_key.encode("utf-8")
        while len(d) < 48:  # 32 key + 16 iv
            d_i = md5(d_i + password + salt).digest()
            d += d_i
        key, iv = d[:32], d[32:48]

        cipher = AES.new(key, AES.MODE_CBC, iv)
        ciphertext = cipher.encrypt(plaintext)
        return base64.b64encode(b"Salted__" + salt + ciphertext).decode("utf-8")

    async def _next_proxy(self) -> str | None:
        return await self._proxy_pool.next() if self._proxy_pool is not None else self._proxy

    async def _mark_proxy_failed(self, proxy: str | None) -> None:
        if self._proxy_pool is not None:
            await self._proxy_pool.mark_failed(proxy)

    async def _mark_proxy_success(self, proxy: str | None) -> None:
        if self._proxy_pool is not None:
            await self._proxy_pool.mark_success(proxy)
