from __future__ import annotations

import asyncio
import logging
import random
from dataclasses import dataclass
from pathlib import Path
from time import time
from urllib.parse import urlparse

import httpx

from .config import Settings

logger = logging.getLogger(__name__)


def parse_http_proxies(text: str, limit: int) -> list[str]:
    proxies: list[str] = []
    seen: set[str] = set()
    for line in text.splitlines():
        proxy = line.strip()
        if not proxy or proxy.startswith("#"):
            continue
        if "://" not in proxy:
            proxy = f"http://{proxy}"
        parsed = urlparse(proxy)
        try:
            port = parsed.port
        except ValueError:
            continue
        if parsed.scheme != "http" or not parsed.hostname or not port or proxy in seen:
            continue
        seen.add(proxy)
        proxies.append(proxy)
    random.shuffle(proxies)
    return proxies[:limit]


def parse_configured_proxies(proxies: tuple[str, ...]) -> list[str]:
    """Accept explicit private HTTP(S)/SOCKS proxy URLs from configuration."""
    accepted: list[str] = []
    seen: set[str] = set()
    for proxy in proxies:
        parsed = urlparse(proxy)
        try:
            port = parsed.port
        except ValueError:
            continue
        if parsed.scheme not in {"http", "https", "socks5", "socks5h"} or not parsed.hostname or not port:
            continue
        if proxy not in seen:
            seen.add(proxy)
            accepted.append(proxy)
    return accepted


@dataclass(frozen=True)
class ProxyStats:
    total: int
    failed: int
    active: int


class ProxyPool:
    def __init__(self, proxies: list[str], cooldown_seconds: float = 5 * 3600) -> None:
        self._proxies = proxies
        self._cooldown_seconds = cooldown_seconds
        self._index = 0
        self._failed_until: dict[str, float] = {}
        self._lock = asyncio.Lock()

    @classmethod
    async def create(cls, settings: Settings) -> "ProxyPool":
        configured = parse_configured_proxies(settings.market_proxy_urls)
        if configured:
            logger.info("Loaded %s configured market proxies", len(configured))
            return cls(configured)
        if not settings.market_proxy_enabled:
            return cls([])

        cache_path = Path(settings.market_proxy_cache_path)
        cached = cache_path.read_text(encoding="utf-8") if cache_path.exists() else ""
        fresh_cache = cache_path.exists() and time() - cache_path.stat().st_mtime < settings.market_proxy_cache_seconds
        text = cached if fresh_cache else ""

        if not text:
            try:
                async with httpx.AsyncClient(timeout=20.0, follow_redirects=True) as client:
                    response = await client.get(settings.market_proxy_source_url)
                    response.raise_for_status()
                    text = response.text
                cache_path.parent.mkdir(parents=True, exist_ok=True)
                cache_path.write_text(text, encoding="utf-8")
            except httpx.HTTPError:
                logger.exception("Could not refresh proxy list; using stale cache if available")
                text = cached

        proxies = parse_http_proxies(text, settings.market_proxy_limit)
        logger.info("Loaded %s market proxies", len(proxies))
        return cls(proxies)

    async def next(self) -> str | None:
        now = time()
        async with self._lock:
            active = [proxy for proxy in self._proxies if self._failed_until.get(proxy, 0.0) <= now]
            if not active:
                return None
            proxy = active[self._index % len(active)]
            self._index += 1
            return proxy

    async def mark_failed(self, proxy: str | None, cooldown_seconds: float | None = None) -> None:
        if not proxy:
            return
        duration = cooldown_seconds if cooldown_seconds is not None else self._cooldown_seconds
        async with self._lock:
            self._failed_until[proxy] = time() + duration
            logger.warning("Proxy %s failed; temporarily removed from pool for %.1f hours", proxy, duration / 3600)

    async def mark_success(self, proxy: str | None) -> None:
        if not proxy:
            return
        async with self._lock:
            self._failed_until.pop(proxy, None)

    def stats(self) -> ProxyStats:
        now = time()
        failed = sum(1 for p in self._proxies if self._failed_until.get(p, 0.0) > now)
        total = len(self._proxies)
        return ProxyStats(total=total, failed=failed, active=max(0, total - failed))
