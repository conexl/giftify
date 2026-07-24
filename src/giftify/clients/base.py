from __future__ import annotations

import asyncio
import logging
from typing import Any, Protocol

import httpx

from giftify.config import Settings
from giftify.domain import Market
from giftify.proxies import ProxyPool

logger = logging.getLogger(__name__)


class TokenProvider(Protocol):
    async def get_token(self) -> str:
        ...

    async def refresh_token(self) -> str:
        ...


class MarketplaceClient:
    def __init__(self, settings: Settings, proxy_pool: ProxyPool, market: Market) -> None:
        self.settings = settings
        self.proxy_pool = proxy_pool
        self.market = market
        self._direct_client: httpx.AsyncClient | None = None

    async def close(self) -> None:
        if self._direct_client is not None:
            await self._direct_client.aclose()
            self._direct_client = None

    def _client_for(self, proxy: str | None) -> tuple[httpx.AsyncClient, bool]:
        timeout = httpx.Timeout(self.settings.market_timeout_seconds, connect=4.0)
        if proxy:
            return httpx.AsyncClient(timeout=timeout, follow_redirects=True, proxy=proxy), True
        if self._direct_client is None:
            self._direct_client = httpx.AsyncClient(timeout=timeout, follow_redirects=True)
        return self._direct_client, False

    async def _request(
        self,
        method: str,
        url: str,
        *,
        headers: dict[str, str],
        use_proxy: bool = True,
        **kwargs: Any,
    ) -> Any:
        if not use_proxy:
            client, close_after_request = self._client_for(None)
            try:
                response = await client.request(method, url, headers=headers, **kwargs)
                if response.status_code >= 500:
                    response.raise_for_status()
                response.raise_for_status()
                return response.json()
            finally:
                if close_after_request:
                    await client.aclose()

        last_error: Exception | None = None
        for attempt in range(self.settings.market_request_attempts):
            proxy = await self.proxy_pool.next()
            client, close_after_request = self._client_for(proxy)
            try:
                response = await client.request(method, url, headers=headers, **kwargs)
            except httpx.TransportError as exc:
                if proxy:
                    await self.proxy_pool.mark_failed(proxy)
                last_error = exc
                logger.warning("%s transport failure on attempt %s", self.market.value, attempt + 1)
                if proxy:
                    try:
                        direct_client, _ = self._client_for(None)
                        dir_resp = await direct_client.request(method, url, headers=headers, **kwargs)
                        if dir_resp.status_code < 500:
                            dir_resp.raise_for_status()
                            return dir_resp.json()
                    except Exception as dir_exc:
                        logger.warning("%s direct fallback failed: %s", self.market.value, dir_exc)
                continue
            finally:
                if close_after_request:
                    await client.aclose()

            if response.status_code == 429 or "if you need more rps" in response.text.lower():
                retry_after = response.headers.get("Retry-After", "5")
                parsed_delay = float(retry_after) if retry_after.replace(".", "", 1).isdigit() else 5.0
                delay = min(max(parsed_delay, 1.0), 5.0)
                logger.warning("%s returned 429 rate limit; sleeping %.1fs", self.market.value, delay)
                await asyncio.sleep(delay)
                continue

            if response.status_code >= 500:
                await self.proxy_pool.mark_failed(proxy)

            response.raise_for_status()
            await self.proxy_pool.mark_success(proxy)
            return response.json()

        if last_error:
            raise last_error
        raise RuntimeError(f"{self.market.value} request failed after retries")


def _absolute_url(value: Any, *, base_url: str = "") -> str | None:
    text = str(value or "").strip()
    if not text:
        return None
    if text.startswith(("http://", "https://")):
        return text
    if text.startswith("//"):
        return f"https:{text}"
    if base_url:
        return f"{base_url.rstrip('/')}/{text.lstrip('/')}"
    return f"https://{text.lstrip('/')}"
