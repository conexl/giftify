from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _dotenv_values(path: str = ".env") -> dict[str, str]:
    file_path = Path(path)
    if not file_path.exists():
        file_path = Path(__file__).resolve().parent.parent.parent / ".env"
    if not file_path.exists():
        return {}
    values: dict[str, str] = {}
    for line in file_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def _env(name: str, default: str | None = None, env_file: dict[str, str] | None = None) -> str | None:
    if name in os.environ:
        return os.environ[name]
    if env_file and name in env_file:
        return env_file[name]
    return default


def _bool_env(name: str, default: bool, env_file: dict[str, str] | None = None) -> bool:
    value = _env(name, env_file=env_file)
    if value is None:
        return default
    return value.lower() in {"1", "true", "yes", "on"}


def _int_env(name: str, default: int, env_file: dict[str, str] | None = None) -> int:
    value = _env(name, env_file=env_file)
    if value is None or not value.isdigit():
        return default
    return int(value)


@dataclass(frozen=True)
class Settings:
    mrkt_base_url: str
    portals_base_url: str
    tunnel_base_url: str
    mrkt_token_file: str
    portals_token_file: str
    tunnel_token_file: str
    market_proxy_enabled: bool
    market_proxy_urls: tuple[str, ...]
    market_proxy_source_url: str
    market_proxy_limit: int
    market_proxy_cache_path: str
    market_proxy_cache_seconds: int
    market_request_attempts: int
    market_timeout_seconds: float
    database_path: str
    purchase_mode: str
    purchase_route_url: str | None
    worker_poll_interval_seconds: float
    worker_limit_per_query: int
    catalog_seed_dir: str | None
    static_tokens_enabled: bool
    tma_refresh_enabled: bool
    tg_app_id: int | None
    tg_app_hash: str | None
    tma_session_path: str
    mrkt_bot_username: str
    mrkt_app_short_name: str
    mrkt_platform: str
    portals_bot_username: str
    portals_app_short_name: str
    portals_platform: str
    tunnel_bot_username: str
    tunnel_app_short_name: str
    tunnel_platform: str
    telegram_proxy: dict[str, str | int] | None
    notification_bot_token: str | None
    notification_chat_id: str | None
    notification_error_cooldown_seconds: int
    allowed_telegram_user_ids: tuple[int, ...]
    tg_bot_token: str | None

    @classmethod
    def from_env(cls) -> "Settings":
        env_file = _dotenv_values()
        tg_app_id = _int_env("TG_APP_ID", 0, env_file) or None
        tg_proxy_host = (_env("TG_PROXY_HOST", "", env_file) or "").strip()
        tg_proxy_port = _int_env("TG_PROXY_PORT", 0, env_file)
        telegram_proxy: dict[str, str | int] | None = None
        if tg_proxy_host and tg_proxy_port:
            telegram_proxy = {
                "scheme": _env("TG_PROXY_SCHEME", "socks5", env_file) or "socks5",
                "hostname": tg_proxy_host,
                "port": tg_proxy_port,
            }
            tg_proxy_user = (_env("TG_PROXY_USER", "", env_file) or "").strip()
            tg_proxy_pass = (_env("TG_PROXY_PASS", "", env_file) or "").strip()
            if tg_proxy_user:
                telegram_proxy["username"] = tg_proxy_user
            if tg_proxy_pass:
                telegram_proxy["password"] = tg_proxy_pass

        allowed_ids_raw = _env("ALLOWED_TELEGRAM_USER_IDS", "", env_file) or ""
        allowed_ids = tuple(
            int(item.strip())
            for item in allowed_ids_raw.replace("\n", ",").split(",")
            if item.strip().isdigit()
        )
        tg_bot_token = (
            _env("TG_BOT_TOKEN", env_file=env_file)
            or _env("NOTIFICATION_BOT_TOKEN", env_file=env_file)
            or None
        )

        db_path_raw = _env("DATABASE_PATH", "data/giftify.sqlite3", env_file) or "data/giftify.sqlite3"
        db_path = Path(db_path_raw)
        if not db_path.is_absolute():
            project_root = Path(__file__).resolve().parent.parent.parent
            db_path = project_root / db_path
        database_path = str(db_path.resolve())

        return cls(
            mrkt_base_url=(_env("MRKT_BASE_URL", "https://api.tgmrkt.io", env_file) or "https://api.tgmrkt.io").rstrip("/"),
            portals_base_url=(_env("PORTALS_BASE_URL", "https://portal-market.com", env_file) or "https://portal-market.com").rstrip("/"),
            tunnel_base_url=(_env("TUNNEL_BASE_URL", "https://gifts3.tonnel.network", env_file) or "https://gifts3.tonnel.network").rstrip("/"),
            mrkt_token_file=_env("MRKT_TOKEN_FILE", ".secrets/mrkt_token.txt", env_file) or ".secrets/mrkt_token.txt",
            portals_token_file=_env("PORTALS_TOKEN_FILE", ".secrets/portals_token.txt", env_file) or ".secrets/portals_token.txt",
            tunnel_token_file=_env("TUNNEL_TOKEN_FILE", ".secrets/tunnel_token.txt", env_file) or ".secrets/tunnel_token.txt",
            market_proxy_enabled=_bool_env("MARKET_PROXY_ENABLED", True, env_file),
            market_proxy_urls=tuple(
                item.strip()
                for item in (_env("MARKET_PROXY_URLS", "", env_file) or "").replace("\n", ",").split(",")
                if item.strip()
            ),
            market_proxy_source_url=_env(
                "MARKET_PROXY_SOURCE_URL",
                "https://raw.githubusercontent.com/iplocate/free-proxy-list/main/protocols/http.txt",
                env_file,
            )
            or "https://raw.githubusercontent.com/iplocate/free-proxy-list/main/protocols/http.txt",
            market_proxy_limit=max(1, _int_env("MARKET_PROXY_LIMIT", 100, env_file)),
            market_proxy_cache_path=_env("MARKET_PROXY_CACHE_PATH", "state/market_proxies.txt", env_file) or "state/market_proxies.txt",
            market_proxy_cache_seconds=max(60, _int_env("MARKET_PROXY_CACHE_SECONDS", 30 * 60, env_file)),
            market_request_attempts=max(1, _int_env("MARKET_REQUEST_ATTEMPTS", 8, env_file)),
            market_timeout_seconds=float(_env("MARKET_TIMEOUT_SECONDS", "20", env_file) or "20"),
            database_path=database_path,
            purchase_mode=_env("PURCHASE_MODE", "dry-run", env_file) or "dry-run",
            purchase_route_url=_env("PURCHASE_ROUTE_URL", env_file=env_file) or None,
            worker_poll_interval_seconds=max(0.05, float(_env("WORKER_POLL_INTERVAL_SECONDS", "0.1", env_file) or "0.1")),
            worker_limit_per_query=max(1, _int_env("WORKER_LIMIT_PER_QUERY", 50, env_file)),
            catalog_seed_dir=_env("CATALOG_SEED_DIR", "/home/conexl/Code/Kalyvan/data/snapshots", env_file),
            static_tokens_enabled=_bool_env("STATIC_TOKENS_ENABLED", True, env_file),
            tma_refresh_enabled=_bool_env("TMA_REFRESH_ENABLED", False, env_file),
            tg_app_id=tg_app_id,
            tg_app_hash=_env("TG_APP_HASH", env_file=env_file) or None,
            tma_session_path=_env("PYROGRAM_SESSION", ".secrets/pyrogram.session", env_file) or ".secrets/pyrogram.session",
            mrkt_bot_username=_env("MRKT_BOT_USERNAME", "mrkt", env_file) or "mrkt",
            mrkt_app_short_name=_env("MRKT_APP_SHORT_NAME", "app", env_file) or "app",
            mrkt_platform=_env("MRKT_PLATFORM", "android", env_file) or "android",
            portals_bot_username=_env("PORTALS_BOT_USERNAME", "portals", env_file) or "portals",
            portals_app_short_name=_env("PORTALS_APP_SHORT_NAME", "market", env_file) or "market",
            portals_platform=_env("PORTALS_PLATFORM", "android", env_file) or "android",
            tunnel_bot_username=_env("TUNNEL_BOT_USERNAME", "tonnel_network_bot", env_file) or "tonnel_network_bot",
            tunnel_app_short_name=_env("TUNNEL_APP_SHORT_NAME", "gifts", env_file) or "gifts",
            tunnel_platform=_env("TUNNEL_PLATFORM", "android", env_file) or "android",
            telegram_proxy=telegram_proxy,
            notification_bot_token=_env("NOTIFICATION_BOT_TOKEN", env_file=env_file) or None,
            notification_chat_id=_env("NOTIFICATION_CHAT_ID", env_file=env_file) or None,
            notification_error_cooldown_seconds=max(
                30, _int_env("NOTIFICATION_ERROR_COOLDOWN_SECONDS", 300, env_file)
            ),
            allowed_telegram_user_ids=allowed_ids,
            tg_bot_token=tg_bot_token,
        )
