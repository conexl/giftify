from __future__ import annotations

import asyncio
from contextlib import suppress
from dataclasses import asdict
from pathlib import Path

import httpx
from fastapi import FastAPI, Query, Response
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .auth import extract_user_id_from_init_data
from .clients import MrktClient, PortalsClient, TunnelClient
from .catalog_seed import seed_catalog_from_snapshots
from .collector import CollectionRequest, GiftCollector
from .config import Settings
from .domain import Market, is_display_value
from .rules import NewRule
from .proxies import ProxyPool
from .purchases import purchase_executor_from_settings
from .storage import SQLiteStore
from .tokens import StaticTokenProvider, TmaTokenProvider
from .worker import AutoBuyWorker
from .notifications import TelegramNotifier
import logging

# Configure logging for giftify module to output to uvicorn/standard output in DEBUG mode
logging.getLogger("giftify").setLevel(logging.DEBUG)
_handler = logging.StreamHandler()
_handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
logging.getLogger("giftify").addHandler(_handler)

TELEGRAM_BACKDROP_COLORS: dict[str, tuple[str, str]] = {
    'Amber': ('#dab345', '#b1802a'),
    'Aquamarine': ('#60b195', '#46abb4'),
    'Azure Blue': ('#5db1cb', '#448bab'),
    'Battleship Grey': ('#8c8c85', '#6c6c66'),
    'Black': ('#363738', '#0e0f0f'),
    'Burgundy': ('#a35e66', '#6d414a'),
    'Burnt Sienna': ('#d66f3c', '#b54b2d'),
    'Camo Green': ('#75944d', '#547341'),
    'Cappuccino': ('#b1907e', '#7c6356'),
    'Caramel': ('#d09932', '#b77431'),
    'Carmine': ('#e0574a', '#a8383b'),
    'Carrot Juice': ('#db9867', '#c76f4f'),
    'Celtic Blue': ('#45b8ed', '#3886d9'),
    'Chestnut': ('#be6f54', '#994838'),
    'Chocolate': ('#a46e58', '#74443b'),
    'Cobalt Blue': ('#6088cf', '#5162b8'),
    'Copper': ('#d08656', '#9d6531'),
    'Coral Red': ('#da896b', '#c4654f'),
    'Cyberpunk': ('#858ff3', '#865fd3'),
    'Dark Green': ('#516341', '#2b452f'),
    'Dark Lilac': ('#b17da5', '#8c577a'),
    'Deep Cyan': ('#31b5aa', '#189599'),
    'Desert Sand': ('#b39f82', '#7e735b'),
    'Electric Indigo': ('#a980f3', '#5b62d8'),
    'Electric Purple': ('#ca70c6', '#9662d4'),
    'Emerald': ('#78c585', '#42a171'),
    'English Violet': ('#b186bb', '#875a91'),
    'Fandango': ('#e28ab6', '#a4588b'),
    'Feldgrau': ('#899288', '#5e6b63'),
    'Fire Engine': ('#f05f4f', '#c43949'),
    'French Blue': ('#5c9bc4', '#37739a'),
    'French Violet': ('#c260e6', '#914ed9'),
    'Grape': ('#9d74c1', '#794da0'),
    'Gunmetal': ('#4c5d63', '#2f3b42'),
    'Gunship Green': ('#558a65', '#3d6657'),
    'Hunter Green': ('#8fae78', '#4b825b'),
    'Indigo Dye': ('#537991', '#416479'),
    'Ivory White': ('#bab6b1', '#a19d97'),
    'Jade Green': ('#55c49c', '#3b9977'),
    'Khaki Green': ('#adb070', '#6b7d54'),
    'Lavender': ('#b789e4', '#8a5abc'),
    'Lemongrass': ('#aeb85a', '#559345'),
    'Light Olive': ('#c2af64', '#887e45'),
    'Malachite': ('#95b457', '#3d9755'),
    'Marine Blue': ('#4e689c', '#3b4b7a'),
    'Mexican Pink': ('#e36692', '#c9497c'),
    'Midnight Blue': ('#5c6985', '#354057'),
    'Mint Green': ('#7ecb82', '#459e5a'),
    'Moonstone': ('#7eb1b4', '#588390'),
    'Mustard': ('#d4980d', '#c47712'),
    'Mystic Pearl': ('#d08b6d', '#b05770'),
    'Navy Blue': ('#6c9edd', '#5c6ec9'),
    'Neon Blue': ('#7596f9', '#6862e4'),
    'Old Gold': ('#b58d38', '#946925'),
    'Onyx Black': ('#4d5254', '#313638'),
    'Orange': ('#d19a3a', '#c06f47'),
    'Pacific Cyan': ('#5abea6', '#3d95ba'),
    'Pacific Green': ('#6fc793', '#3b9c84'),
    'Persimmon': ('#e7a75a', '#c5675f'),
    'Pine Green': ('#6ba97c', '#3e7970'),
    'Pistachio': ('#97b07c', '#5c814c'),
    'Platinum': ('#b2aea7', '#88847e'),
    'Pure Gold': ('#ccab41', '#987b32'),
    'Purple': ('#ae6cae', '#844784'),
    'Ranger Green': ('#5f7849', '#3c4f3b'),
    'Raspberry': ('#e07b85', '#b65980'),
    'Rifle Green': ('#64695c', '#4b5241'),
    'Roman Silver': ('#a3a8b5', '#7c808a'),
    'Rosewood': ('#b77a77', '#814c52'),
    'Sapphire': ('#58a3c8', '#5379c2'),
    'Satin Gold': ('#bf9b47', '#8d7739'),
    'Seal Brown': ('#664d45', '#47362e'),
    'Shamrock Green': ('#8ab163', '#559345'),
    'Silver Blue': ('#80a4b8', '#607c91'),
    'Sky Blue': ('#58b4c8', '#538bc2'),
    'Steel Grey': ('#97a2ac', '#63727c'),
    'Strawberry': ('#dd8e6f', '#b75a60'),
    'Tactical Pine': ('#44826b', '#2f6369'),
    'Tomato': ('#e6793e', '#d44e3f'),
    'Turquoise': ('#5ec0b8', '#3d928e'),
}

class RuleCreateRequest(BaseModel):
    user_id: int = Field(ge=0)
    collection: str = Field(min_length=1)
    max_price_ton: float = Field(gt=0)
    market: Market | None = None
    model: str | None = None
    backdrop: str | None = None
    enabled: bool = True
    max_spend_ton: float | None = Field(default=None, gt=0)


class RuleEnabledRequest(BaseModel):
    enabled: bool


class BotPauseRequest(BaseModel):
    paused: bool


_ACCESS_DENIED_HTML = """<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Giftify — Доступ ограничен</title>
    <script src="https://telegram.org/js/telegram-web-app.js"></script>
    <script>
      try {
        const tg = window.Telegram?.WebApp;
        tg?.ready?.();
        const initData = tg?.initData || new URLSearchParams(location.search).get('tgWebAppData') || new URLSearchParams(location.hash.slice(1)).get('tgWebAppData') || new URLSearchParams(location.search).get('init_data');
        if (initData && !location.search.includes('init_data=')) {
          location.replace('/app?init_data=' + encodeURIComponent(initData));
        }
      } catch (e) {}
    </script>
    <style>
        body { background: #020617; color: #f8fafc; font-family: system-ui, -apple-system, sans-serif; display: flex; align-items: center; justify-content: center; min-height: 100vh; margin: 0; padding: 20px; box-sizing: border-box; text-align: center; }
        .card { background: #0f172a; border: 1px solid #1e293b; border-radius: 16px; padding: 40px 24px; max-width: 440px; width: 100%; box-shadow: 0 20px 25px -5px rgba(0,0,0,0.5); }
        .icon { font-size: 48px; margin-bottom: 16px; }
        h1 { font-size: 22px; font-weight: 700; margin: 0 0 12px 0; color: #f43f5e; }
        p { font-size: 14px; color: #94a3b8; line-height: 1.6; margin: 0 0 24px 0; }
        .badge { display: inline-block; background: #1e293b; color: #38bdf8; padding: 6px 12px; border-radius: 8px; font-size: 12px; font-weight: 600; font-family: monospace; }
    </style>
</head>
<body>
    <div class="card">
        <div class="icon">🔒</div>
        <h1>Доступ ограничен</h1>
        <p>Приложение доступно только через Telegram Mini App для разрешённых пользователей.</p>
        <div class="badge">giftify.xorx.dev</div>
    </div>
</body>
</html>"""


def create_app() -> FastAPI:
    app = FastAPI(title="Giftify", version="0.1.0")
    settings = Settings.from_env()
    state: dict[str, object] = {}
    static_dir = Path(__file__).parent / "static"
    app.mount("/static", StaticFiles(directory=static_dir), name="static")

    @app.middleware("http")
    async def enforce_telegram_auth(request, call_next):
        if request.url.path.startswith("/static/"):
            response = await call_next(request)
            response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
            response.headers["Pragma"] = "no-cache"
            return response

        allowed_ids = settings.allowed_telegram_user_ids
        if not allowed_ids:
            return await call_next(request)

        auth_header = request.headers.get("Authorization", "")
        token_from_auth = ""
        if auth_header.lower().startswith("tma "):
            token_from_auth = auth_header[4:].strip()
        elif auth_header.lower().startswith("bearer "):
            token_from_auth = auth_header[7:].strip()

        init_data = (
            request.headers.get("X-Telegram-Init-Data")
            or request.headers.get("X-TG-INIT-DATA")
            or token_from_auth
            or request.query_params.get("init_data")
            or request.query_params.get("tgWebAppData")
            or ""
        )

        user_id = extract_user_id_from_init_data(init_data, settings.tg_bot_token)

        # Dev mode: if 0 is in allowed_ids, allow unauthenticated browser access (user_id treated as 0).
        dev_mode = 0 in allowed_ids

        # Allow page requests (/ and /app) to load app.html so Telegram WebApp JS can initialize and provide initData.
        if not request.url.path.startswith("/api/v1/"):
            return await call_next(request)

        # /api/v1/dev-mode is always public — frontend needs it to decide whether to show auth wall.
        if request.url.path == "/api/v1/dev-mode":
            return await call_next(request)

        # For API requests (/api/v1/...)
        if user_id is None:
            if dev_mode:
                # Inject synthetic X-Dev-User-Id header so downstream handlers can use user_id=0.
                from starlette.datastructures import MutableHeaders
                headers = MutableHeaders(scope=request.scope)
                headers.append("X-Dev-User-Id", "0")
                return await call_next(request)
            return JSONResponse(
                status_code=401,
                content={"detail": "Доступ запрещён. Откройте приложение через Telegram Mini App."}
            )

        if user_id not in allowed_ids:
            return JSONResponse(
                status_code=403,
                content={"detail": f"Доступ запрещён для вашего Telegram ID ({user_id})."}
            )

        return await call_next(request)

    @app.get("/")
    async def index() -> FileResponse:
        return FileResponse(static_dir / "app.html")

    @app.get("/app")
    async def mini_app() -> FileResponse:
        return FileResponse(static_dir / "app.html")

    @app.on_event("startup")
    async def startup() -> None:
        proxy_pool = await ProxyPool.create(settings)
        state["proxy_pool"] = proxy_pool
        state["store"] = SQLiteStore(settings.database_path)
        seed_catalog_from_snapshots(state["store"], settings.catalog_seed_dir)

        mrkt_token_provider = TmaTokenProvider(
            settings, "mrkt", settings.mrkt_token_file, ttl_seconds=3600
        )
        portals_token_provider = TmaTokenProvider(
            settings, "portals", settings.portals_token_file, ttl_seconds=3600
        )
        tunnel_token_provider = TmaTokenProvider(
            settings, "tunnel", settings.tunnel_token_file, ttl_seconds=3600
        )

        mrkt_client = MrktClient(settings, proxy_pool, mrkt_token_provider)
        state["mrkt_client"] = mrkt_client
        state["mrkt_catalog_collections"] = []
        state["mrkt_catalog_models"] = {}
        state["collector"] = GiftCollector(
            mrkt_client,
            PortalsClient(settings, proxy_pool, portals_token_provider),
            TunnelClient(settings, proxy_pool, tunnel_token_provider),
        )
        collector = state["collector"]
        store = state["store"]
        assert isinstance(collector, GiftCollector)
        assert isinstance(store, SQLiteStore)

        executor = purchase_executor_from_settings(
            settings,
            token_provider=mrkt_token_provider,
            portals_token_provider=portals_token_provider,
            tunnel_token_provider=tunnel_token_provider,
            proxy_pool=proxy_pool,
        )
        worker = AutoBuyWorker(collector, store, executor, notifier=TelegramNotifier.from_settings(settings))
        state["worker"] = worker
        state["worker_task"] = asyncio.create_task(
            worker.run_forever(
                interval_seconds=settings.worker_poll_interval_seconds,
                limit_per_market=settings.worker_limit_per_query,
            )
        )
        state["catalog_task"] = asyncio.create_task(_refresh_mrkt_catalog(state, mrkt_client))

    @app.on_event("shutdown")
    async def shutdown() -> None:
        worker_task = state.get("worker_task")
        if isinstance(worker_task, asyncio.Task):
            worker_task.cancel()
            with suppress(asyncio.CancelledError):
                await worker_task
        catalog_task = state.get("catalog_task")
        if isinstance(catalog_task, asyncio.Task):
            catalog_task.cancel()
            with suppress(asyncio.CancelledError):
                await catalog_task
        store = state.get("store")
        if isinstance(store, SQLiteStore):
            store.close()
        collector = state.get("collector")
        if isinstance(collector, GiftCollector):
            await collector.close()

    @app.get("/health")
    async def health() -> dict[str, object]:
        proxy_pool = state.get("proxy_pool")
        proxy_stats = asdict(proxy_pool.stats()) if isinstance(proxy_pool, ProxyPool) else None
        worker_task = state.get("worker_task")
        worker_running = isinstance(worker_task, asyncio.Task) and not worker_task.done()
        return {"status": "ok", "proxy": proxy_stats, "worker": {"running": worker_running}}

    @app.get("/api/v1/dev-mode")
    async def dev_mode_info() -> dict[str, object]:
        """Public endpoint: tells the frontend whether dev mode (user_id=0 bypass) is active."""
        is_dev = 0 in settings.allowed_telegram_user_ids
        return {"dev": is_dev, "user_id": 0 if is_dev else None}



    @app.get("/api/v1/rules")
    async def rules(user_id: int | None = Query(None, ge=0), enabled_only: bool = Query(False)) -> dict[str, object]:
        store = state["store"]
        assert isinstance(store, SQLiteStore)
        items = store.list_rules(enabled_only=enabled_only, user_id=None)

        mrkt_client = state.get("mrkt_client")
        mrkt_cache = state.get("mrkt_catalog_models")
        if not isinstance(mrkt_cache, dict):
            mrkt_cache = {}
            state["mrkt_catalog_models"] = mrkt_cache

        mrkt_collections_raw = state.get("mrkt_catalog_collections", [])
        mrkt_col_photos: dict[str, str] = {}
        for c in mrkt_collections_raw:
            if isinstance(c, dict) and c.get("name") and c.get("photo_url"):
                mrkt_col_photos[c["name"]] = c["photo_url"]

        result_rules = []
        for item in items:
            rule_dict = asdict(item)
            photo = None
            if item.collection and item.model:
                try:
                    mrkt_key = f"{item.collection}_{item.model}".encode("utf-8").hex()
                    photo = f"https://cdn.tgmrkt.io/gifts/stickers/thumbnails/{mrkt_key}.webp"
                except Exception:
                    photo = None

            if not photo and item.collection:
                photo = mrkt_col_photos.get(item.collection) or db_col_photos.get(item.collection)

            if photo and "fragment.com" in photo:
                photo = None

            rule_dict["photo_url"] = photo
            result_rules.append(rule_dict)

        return {"total": len(result_rules), "rules": result_rules}

    @app.get("/api/v1/catalog")
    async def catalog(response: Response) -> dict[str, object]:
        response.headers["Cache-Control"] = "public, max-age=3600"
        store = state["store"]
        assert isinstance(store, SQLiteStore)
        options = [
            option
            for option in store.list_catalog()
            if _is_public_catalog_value(option.collection)
            and _is_public_catalog_value(option.model)
            and _is_public_catalog_value(option.backdrop)
            and _is_public_catalog_value(option.symbol)
        ]
        dynamic_collections_raw = state.get("mrkt_catalog_collections", [])
        dynamic_collection_names: set[str] = set()
        collection_photos: dict[str, str | None] = {}
        for item in dynamic_collections_raw:
            if isinstance(item, dict):
                name = item.get("name", "")
                if name and _is_public_catalog_value(name):
                    dynamic_collection_names.add(name)
                    if item.get("photo_url"):
                        collection_photos[name] = item["photo_url"]
            elif isinstance(item, str) and _is_public_catalog_value(item):
                dynamic_collection_names.add(item)

        db_collection_photos = store.get_collection_photos()
        for name, photo in db_collection_photos.items():
            if name not in collection_photos or not collection_photos[name]:
                collection_photos[name] = photo

        all_collection_names = sorted(
            {option.collection for option in options} | dynamic_collection_names,
            key=str.casefold,
        )
        collections = [
            {"name": name, "photo_url": collection_photos.get(name)}
            for name in all_collection_names
        ]
        models_by_collection: dict[str, list[dict]] = {}
        db_model_photos = store.get_model_photos()
        backdrops_by_collection: dict[str, list[dict]] = {}
        for col_name in all_collection_names:
            collection_options = [option for option in options if option.collection == col_name]
            model_names = sorted(
                {option.model for option in collection_options if option.model},
                key=str.casefold,
            )
            models_by_collection[col_name] = [
                {"name": m_name, "photo_url": db_model_photos.get(m_name)}
                for m_name in model_names
            ]
            backdrop_names = sorted(
                {option.backdrop for option in collection_options if option.backdrop},
                key=str.casefold,
            )
            backdrops_by_collection[col_name] = [
                {
                    "name": b_name,
                    "center_color": TELEGRAM_BACKDROP_COLORS.get(b_name, (None, None))[0],
                    "edge_color": TELEGRAM_BACKDROP_COLORS.get(b_name, (None, None))[1],
                }
                for b_name in backdrop_names
            ]
        return {
            "total": len(options),
            "collections": collections,
            "models_by_collection": models_by_collection,
            "backdrops_by_collection": backdrops_by_collection,
        }

    @app.get("/api/v1/catalog/models")
    async def catalog_models(response: Response, collection: str = Query(..., min_length=1)) -> dict[str, object]:
        response.headers["Cache-Control"] = "public, max-age=3600"
        normalized_collection = collection.strip()
        norm_key = normalized_collection.replace("’", "'").replace("‘", "'").casefold()
        store = state["store"]
        assert isinstance(store, SQLiteStore)
        db_model_photos = store.get_model_photos(normalized_collection)

        # Get options from local store for instant response
        options = store.list_catalog()
        sqlite_models = sorted(
            {option.model for option in options if option.collection and option.collection.replace("’", "'").replace("‘", "'").casefold() == norm_key and option.model},
            key=str.casefold,
        )

        cache = state.get("mrkt_catalog_models")
        if not isinstance(cache, dict):
            cache = {}
            state["mrkt_catalog_models"] = cache
        models_raw = cache.get(normalized_collection)
        if models_raw is None or len(models_raw) == 0:
            mrkt_client = state.get("mrkt_client")
            if isinstance(mrkt_client, MrktClient):
                with suppress(Exception):
                    models_raw = await asyncio.wait_for(mrkt_client.catalog_models(normalized_collection), timeout=5.0)
            if models_raw is None:
                models_raw = []
            cache[normalized_collection] = models_raw

        # Format models as list[dict] with name, photo_url and rarity_per_mille
        result_models: list[dict[str, Any]] = []
        seen_names: set[str] = set()
        for item in models_raw:
            if isinstance(item, dict):
                name = item.get("name", "")
                if name and name not in seen_names:
                    seen_names.add(name)
                    photo = item.get("photo_url") or db_model_photos.get(name)
                    rarity = item.get("rarity_per_mille") or item.get("rarityPerMille")
                    result_models.append({"name": name, "photo_url": photo, "rarity_per_mille": rarity})
            elif isinstance(item, str) and item not in seen_names:
                seen_names.add(item)
                result_models.append({"name": item, "photo_url": db_model_photos.get(item), "rarity_per_mille": None})

        # Always merge all models from local store and history
        all_local_names = set(sqlite_models) | set(db_model_photos.keys())
        for name in sorted(all_local_names, key=str.casefold):
            if name not in seen_names:
                seen_names.add(name)
                result_models.append({"name": name, "photo_url": db_model_photos.get(name), "rarity_per_mille": None})

        return {"collection": normalized_collection, "models": result_models}

    @app.get("/api/v1/catalog/backdrops")
    async def catalog_backdrops(response: Response, collection: str = Query(..., min_length=1)) -> dict[str, object]:
        response.headers["Cache-Control"] = "public, max-age=3600"
        normalized_collection = collection.strip()
        norm_key = normalized_collection.replace("’", "'").replace("‘", "'").casefold()
        store = state["store"]
        assert isinstance(store, SQLiteStore)

        options = store.list_catalog()
        sqlite_backdrops = sorted(
            {option.backdrop for option in options if option.collection and option.collection.replace("’", "'").replace("‘", "'").casefold() == norm_key and option.backdrop},
            key=str.casefold,
        )

        cache = state.get("mrkt_catalog_backdrops")
        if not isinstance(cache, dict):
            cache = {}
            state["mrkt_catalog_backdrops"] = cache

        backdrops_raw = cache.get(normalized_collection)
        if backdrops_raw is None or len(backdrops_raw) == 0:
            mrkt_client = state.get("mrkt_client")
            if isinstance(mrkt_client, MrktClient):
                with suppress(Exception):
                    backdrops_raw = await asyncio.wait_for(mrkt_client.catalog_backdrops(normalized_collection), timeout=5.0)
            if backdrops_raw is None:
                backdrops_raw = []
            cache[normalized_collection] = backdrops_raw

        result_backdrops: list[dict[str, Any]] = []
        seen_names: set[str] = set()

        for item in backdrops_raw:
            if isinstance(item, dict):
                name = item.get("name", "")
                if name and name not in seen_names:
                    seen_names.add(name)
                    c_color = item.get("center_color") or TELEGRAM_BACKDROP_COLORS.get(name, (None, None))[0]
                    e_color = item.get("edge_color") or TELEGRAM_BACKDROP_COLORS.get(name, (None, None))[1]
                    result_backdrops.append({
                        "name": name,
                        "center_color": c_color,
                        "edge_color": e_color,
                    })
            elif isinstance(item, str) and item not in seen_names:
                seen_names.add(item)
                colors = TELEGRAM_BACKDROP_COLORS.get(item, (None, None))
                result_backdrops.append({"name": item, "center_color": colors[0], "edge_color": colors[1]})

        for name in sqlite_backdrops:
            if name not in seen_names:
                seen_names.add(name)
                colors = TELEGRAM_BACKDROP_COLORS.get(name, (None, None))
                result_backdrops.append({"name": name, "center_color": colors[0], "edge_color": colors[1]})

        return {"collection": normalized_collection, "backdrops": result_backdrops}

    @app.post("/api/v1/rules")
    async def create_rule(payload: RuleCreateRequest) -> dict[str, object]:
        store = state["store"]
        assert isinstance(store, SQLiteStore)
        rule = store.create_rule(
            NewRule(
                user_id=payload.user_id,
                market=payload.market,
                collection=payload.collection,
                model=payload.model,
                backdrop=payload.backdrop,
                max_price_ton=payload.max_price_ton,
                enabled=payload.enabled,
                max_spend_ton=payload.max_spend_ton,
            )
        )
        return {"rule": asdict(rule)}

    @app.delete("/api/v1/rules/{rule_id}")
    async def delete_rule(rule_id: int, user_id: int | None = Query(None)) -> dict[str, object]:
        store = state["store"]
        assert isinstance(store, SQLiteStore)
        deleted = store.delete_rule(rule_id, user_id=None)
        return {"deleted": deleted}

    @app.patch("/api/v1/rules/{rule_id}/enabled")
    async def set_rule_enabled(rule_id: int, payload: RuleEnabledRequest, user_id: int | None = Query(None)) -> dict[str, object]:
        store = state["store"]
        assert isinstance(store, SQLiteStore)
        updated = store.set_rule_enabled(rule_id, payload.enabled, user_id=None)
        return {"updated": updated}

    @app.get("/api/v1/bot-status")
    async def bot_status() -> dict[str, object]:
        store = state["store"]
        worker = state.get("worker")
        assert isinstance(store, SQLiteStore)
        report = worker.last_report if isinstance(worker, AutoBuyWorker) else None
        return {
            "paused": store.is_bot_paused(),
            "purchase_mode": settings.purchase_mode,
            "active_rules": len(store.list_rules(enabled_only=True)),
            "last_checked_at": worker.last_checked_at if isinstance(worker, AutoBuyWorker) else None,
            "last_error": worker.last_error if isinstance(worker, AutoBuyWorker) else None,
            "last_purchase_error": (
                {"status": worker.last_purchase_error.status.value, "message": worker.last_purchase_error.message}
                if isinstance(worker, AutoBuyWorker) and worker.last_purchase_error is not None
                else None
            ),
            "last_report": asdict(report) if report else None,
        }

    @app.put("/api/v1/bot-status/pause")
    async def set_bot_paused(payload: BotPauseRequest) -> dict[str, object]:
        store = state["store"]
        assert isinstance(store, SQLiteStore)
        store.set_bot_paused(payload.paused)
        return {"paused": store.is_bot_paused()}

    @app.get("/api/v1/purchase-attempts")
    async def purchase_attempts() -> dict[str, object]:
        store = state["store"]
        assert isinstance(store, SQLiteStore)
        attempts = store.list_attempts()
        return {"total": len(attempts), "attempts": [asdict(item) for item in attempts]}

    @app.get("/api/v1/purchases")
    async def purchases() -> dict[str, object]:
        store = state["store"]
        assert isinstance(store, SQLiteStore)
        items = store.list_purchases()
        return {"total": len(items), "purchases": [asdict(item) for item in items]}

    @app.get("/api/v1/saved-gifts")
    async def saved_gifts(limit: int = Query(200, ge=1, le=500)) -> dict[str, object]:
        store = state["store"]
        assert isinstance(store, SQLiteStore)
        items = store.list_saved_gifts(limit=limit)
        return {"total": len(items), "gifts": [asdict(item) for item in items]}

    @app.delete("/api/v1/saved-gifts/{gift_id}")
    async def archive_saved_gift(gift_id: int) -> dict[str, object]:
        store = state["store"]
        assert isinstance(store, SQLiteStore)
        archived = store.archive_saved_gift(gift_id)
        return {"success": archived}

    @app.post("/api/v1/saved-gifts/archive-all")
    async def archive_all_saved_gifts() -> dict[str, object]:
        store = state["store"]
        assert isinstance(store, SQLiteStore)
        count = store.archive_all_saved_gifts()
        return {"archived_count": count}

    @app.post("/api/v1/worker/poll")
    async def poll_worker(limit_per_market: int = Query(50, ge=1, le=100)) -> dict[str, object]:
        collector = state["collector"]
        store = state["store"]
        assert isinstance(collector, GiftCollector)
        assert isinstance(store, SQLiteStore)
        report = await AutoBuyWorker(collector, store, purchase_executor_from_settings(settings)).poll_once(limit_per_market=limit_per_market)
        return {"report": asdict(report)}

    @app.get("/api/v1/gifts")
    async def gifts(
        limit_per_market: int = Query(20, ge=1, le=100),
        include_sales: bool = Query(True),
        max_price_ton: float | None = Query(None, gt=0),
        markets: list[Market] = Query(default=[Market.MRKT, Market.PORTALS]),
    ) -> dict[str, object]:
        collector = state["collector"]
        assert isinstance(collector, GiftCollector)
        snapshots = await collector.collect(
            CollectionRequest(
                markets=tuple(markets),
                limit_per_market=limit_per_market,
                include_sales=include_sales,
                max_price_ton=max_price_ton,
            )
        )
        store = state["store"]
        assert isinstance(store, SQLiteStore)
        listings = [snapshot.listing for snapshot in snapshots]
        store.upsert_catalog(listings)
        store.upsert_listing_history(listings)
        return {
            "total": len(snapshots),
            "gifts": [
                {
                    "listing": asdict(snapshot.listing),
                    "sales": [asdict(sale) for sale in snapshot.sales],
                }
                for snapshot in snapshots
            ],
        }

    @app.get("/api/v1/listings")
    async def listing_history(
        limit: int = Query(500, ge=1, le=1000),
        market: Market | None = Query(None),
        collection: str | None = Query(None),
        model: str | None = Query(None),
        backdrop: str | None = Query(None),
        max_price_ton: float | None = Query(None, gt=0),
        query: str | None = Query(None),
    ) -> dict[str, object]:
        store = state["store"]
        assert isinstance(store, SQLiteStore)
        records = [
            item
            for item in store.list_listing_history(
                market=market,
                collection=collection or None,
                model=model or None,
                backdrop=backdrop or None,
                max_price_ton=max_price_ton,
                query=query or None,
                limit=limit,
            )
            if _is_public_catalog_value(item.collection)
            and _is_public_catalog_value(item.title)
            and _is_public_catalog_value(item.model)
            and _is_public_catalog_value(item.backdrop)
            and _is_public_catalog_value(item.symbol)
        ]
        return {"total": len(records), "listings": [asdict(item) for item in records]}

    return app


async def _refresh_mrkt_catalog(state: dict[str, object], client: MrktClient) -> None:
    try:
        state["mrkt_catalog_collections"] = await client.catalog_collections()
    except Exception:
        # Catalog suggestions are optional and must never affect the buyer.
        state["mrkt_catalog_collections"] = []


def _is_public_catalog_value(value: str | None) -> bool:
    return not value or is_display_value(value)
