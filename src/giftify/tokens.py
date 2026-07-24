from __future__ import annotations

import asyncio
import logging
import threading
import time
import urllib.parse
from pathlib import Path

import httpx

from .config import Settings

logger = logging.getLogger(__name__)
_pyrogram_lock = threading.Lock()


def extract_init_data(webview_url: str) -> str:
    parsed = urllib.parse.urlparse(webview_url)
    query = urllib.parse.parse_qs(parsed.query)
    value = query.get("tgWebAppData", [""])[0]
    if not value and parsed.fragment:
        value = urllib.parse.parse_qs(parsed.fragment.lstrip("?")).get("tgWebAppData", [""])[0]
    return value or ""


class StaticTokenProvider:
    """Reads marketplace TMA/API token from disk on every request."""

    def __init__(self, token_file: str) -> None:
        self._path = Path(token_file)

    async def get_token(self) -> str:
        return self._read_token()

    async def refresh_token(self) -> str:
        return self._read_token()

    def _read_token(self) -> str:
        if not self._path.exists():
            return ""
        return _normalize_token(self._path.read_text(encoding="utf-8"))


class TmaTokenProvider:
    """Refreshes marketplace credentials from a copied Pyrogram session."""

    def __init__(self, settings: Settings, marketplace: str, token_file: str, *, ttl_seconds: int) -> None:
        self._settings = settings
        self._marketplace = marketplace
        self._token_path = Path(token_file)
        self._ttl_seconds = ttl_seconds
        self._token = ""
        self._issued_at = 0.0
        self._lock = asyncio.Lock()
        # A copied token can belong to a previous Telegram account.  When
        # static tokens are disabled, always obtain the first token from the
        # configured Pyrogram session instead of inheriting that account.
        if settings.static_tokens_enabled:
            self._load_token_file()

    async def get_token(self) -> str:
        if self._settings.static_tokens_enabled:
            static_token = self._read_token_file()
            if static_token and self._is_fresh_file_token():
                return static_token
        if self._token and self._is_current():
            return self._token
        if not self._settings.tma_refresh_enabled:
            return self._read_token_file()
        return await self.refresh_token()

    async def refresh_token(self) -> str:
        if not self._settings.tma_refresh_enabled:
            return self._read_token_file()
        async with self._lock:
            token = await asyncio.to_thread(self._refresh_sync)
            self._token = token
            self._issued_at = time.time()
            self._token_path.parent.mkdir(parents=True, exist_ok=True)
            self._token_path.write_text(token, encoding="utf-8")
            self._token_path.chmod(0o600)
            return token

    def _load_token_file(self) -> None:
        token = self._read_token_file()
        if token:
            self._token = token
            self._issued_at = self._token_path.stat().st_mtime

    def _read_token_file(self) -> str:
        if not self._token_path.exists():
            return ""
        return _normalize_token(self._token_path.read_text(encoding="utf-8"))

    def _is_current(self) -> bool:
        return bool(self._token) and time.time() - self._issued_at < self._ttl_seconds

    def _is_fresh_file_token(self) -> bool:
        return self._token_path.exists() and time.time() - self._token_path.stat().st_mtime < self._ttl_seconds

    def _refresh_sync(self) -> str:
        logger.debug("Refreshing TMA token for %s", self._marketplace)
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            init_data = self._request_webview_init_data()
            if self._marketplace == "mrkt":
                return self._exchange_mrkt_init_data(init_data)
            if self._marketplace == "tunnel":
                return init_data
            return f"tma {urllib.parse.quote(urllib.parse.unquote(init_data), safe='=&')}"
        finally:
            loop.close()
            asyncio.set_event_loop(None)

    def _request_webview_init_data(self) -> str:
        if not self._settings.tg_app_id or not self._settings.tg_app_hash:
            raise RuntimeError("TG_APP_ID and TG_APP_HASH are required for TMA token refresh")

        session_path = Path(self._settings.tma_session_path).expanduser().resolve()
        if not session_path.exists():
            raise FileNotFoundError(f"Pyrogram session not found: {session_path}")

        with _pyrogram_lock:
            if self._settings.telegram_proxy:
                try:
                    logger.debug("Connecting to Telegram directly without proxy...")
                    return self._fetch_init_data(session_path, proxy=None)
                except Exception as exc:
                    logger.warning("Direct Telegram connection failed (%s); falling back to proxy", exc)
                    return self._fetch_init_data(session_path, proxy=self._settings.telegram_proxy)
            return self._fetch_init_data(session_path, proxy=None)

    def _fetch_init_data(self, session_path: Path, proxy: dict[str, Any] | None) -> str:
        from pyrogram import Client
        from pyrogram.raw import functions, types

        bot_username, app_short_name, platform = self._marketplace_config()
        session_name = session_path.stem
        with Client(
            name=session_name,
            api_id=self._settings.tg_app_id,
            api_hash=self._settings.tg_app_hash,
            proxy=proxy,
            workdir=str(session_path.parent),
            no_updates=True,
        ) as app:
            bot = app.get_users(bot_username)
            peer = app.resolve_peer(bot_username)
            access_hash = getattr(bot, "access_hash", None) or getattr(getattr(bot, "raw", None), "access_hash", None)
            if not access_hash:
                resolved = app.invoke(functions.contacts.ResolveUsername(username=bot_username))
                access_hash = next(
                    (user.access_hash for user in resolved.users if isinstance(user, types.User) and user.id == bot.id),
                    None,
                )
            if not access_hash:
                raise RuntimeError(f"Could not resolve access hash for @{bot_username}")
            input_bot = types.InputUser(user_id=bot.id, access_hash=access_hash)
            result = app.invoke(
                functions.messages.RequestAppWebView(
                    peer=peer,
                    app=types.InputBotAppShortName(bot_id=input_bot, short_name=app_short_name),
                    platform=platform,
                )
            )

        init_data = extract_init_data(result.url)
        if not init_data:
            raise RuntimeError(f"Telegram did not return init data for @{bot_username}")
        return init_data

    def _marketplace_config(self) -> tuple[str, str, str]:
        if self._marketplace == "mrkt":
            return self._settings.mrkt_bot_username, self._settings.mrkt_app_short_name, self._settings.mrkt_platform
        if self._marketplace == "tunnel":
            return self._settings.tunnel_bot_username, self._settings.tunnel_app_short_name, self._settings.tunnel_platform
        return self._settings.portals_bot_username, self._settings.portals_app_short_name, self._settings.portals_platform

    def _exchange_mrkt_init_data(self, init_data: str) -> str:
        headers = {
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64; rv:148.0) Gecko/20100101 Firefox/148.0",
            "Accept": "application/json, text/plain, */*",
            "Content-Type": "application/json",
            "Origin": "https://cdn.tgmrkt.io",
            "Referer": "https://cdn.tgmrkt.io/",
        }
        with httpx.Client(timeout=30.0, follow_redirects=True) as client:
            response = client.post(f"{self._settings.mrkt_base_url}/api/v1/auth", headers=headers, json={"data": init_data})
            response.raise_for_status()
        token = _normalize_token(response.json().get("token"))
        if not token:
            raise RuntimeError("MRKT auth response did not contain a token")
        return token


def _normalize_token(token: object) -> str:
    value = str(token or "").strip()
    for prefix in ("Bearer ", "bearer ", "tma "):
        if value.startswith(prefix):
            return value[len(prefix) :].strip()
    return value
