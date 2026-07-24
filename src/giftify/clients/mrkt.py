from __future__ import annotations

from typing import Any
import httpx

from giftify.config import Settings
from giftify.domain import GiftListing, Market, Sale, display_value, nano_to_ton, number
from giftify.proxies import ProxyPool
from .base import MarketplaceClient, TokenProvider, _absolute_url

MRKT_CDN_BASE_URL = "https://cdn.tgmrkt.io/"


def _norm_apostrophe(value: str | None) -> str:
    return (value or "").replace("’", "'").replace("‘", "'").strip().casefold()


class MrktClient(MarketplaceClient):
    def __init__(self, settings: Settings, proxy_pool: ProxyPool, token_provider: TokenProvider) -> None:
        super().__init__(settings, proxy_pool, Market.MRKT)
        self._token_provider = token_provider

    async def headers(self) -> dict[str, str]:
        token = await self._token_provider.get_token()
        return {
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64; rv:152.0) Gecko/20100101 Firefox/152.0",
            "Authorization": token,
            "Cookie": f"access_token={token}",
            "Origin": "https://cdn.tgmrkt.io",
            "Referer": "https://cdn.tgmrkt.io/",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

    async def listings(
        self,
        *,
        count: int,
        cursor: str = "",
        collection_names: list[str] | None = None,
        model_names: list[str] | None = None,
        backdrop_names: list[str] | None = None,
        max_price_ton: float | None = None,
    ) -> list[GiftListing]:
        payload: dict[str, Any] = {
            "count": count,
            "cursor": cursor,
            "collectionNames": collection_names or [],
            "modelNames": model_names or [],
            "backdropNames": backdrop_names or [],
            "symbolNames": [],
            "ordering": "None",
            "lowToHigh": False,
        }
        if max_price_ton is not None:
            payload["maxPrice"] = int(max_price_ton * 1_000_000_000)

        result = await self._request_with_token_refresh("POST", f"{self.settings.mrkt_base_url}/api/v1/gifts/saling", json=payload)
        return [listing for item in result.get("gifts", []) if (listing := self.parse_listing(item))]

    async def catalog_collections(self) -> list[dict]:
        result = await self._request_with_token_refresh(
            "GET", f"{self.settings.mrkt_base_url}/api/v1/gifts/collections", use_proxy=False
        )
        records = result if isinstance(result, list) else result.get("collections", [])
        seen: dict[str, dict] = {}
        for item in records:
            if not isinstance(item, dict):
                continue
            name = display_value(item.get("title")) or display_value(item.get("name"))
            if not name or name in seen:
                continue
            thumb_key = (
                item.get("modelStickerThumbnailKey")
                or item.get("stickerThumbnailKey")
                or item.get("symbolStickerThumbnailKey")
                or item.get("thumbnailKey")
                or item.get("imageKey")
            )
            photo_url = _absolute_url(thumb_key, base_url=MRKT_CDN_BASE_URL) if thumb_key else None
            seen[name] = {"name": name, "photo_url": photo_url}
        return sorted(seen.values(), key=lambda x: x["name"].casefold())

    async def catalog_models(self, collection: str) -> list[dict]:
        collections_payload = [collection]
        if "'" in collection or "’" in collection or "‘" in collection:
            curly = collection.replace("'", "’")
            straight = collection.replace("’", "'").replace("‘", "'")
            collections_payload = list(dict.fromkeys([collection, curly, straight]))

        result = await self._request_with_token_refresh(
            "POST",
            f"{self.settings.mrkt_base_url}/api/v1/gifts/models",
            json={"collections": collections_payload},
            use_proxy=False,
        )
        records = result if isinstance(result, list) else result.get("models", [])
        seen: dict[str, dict] = {}
        target_norms = {_norm_apostrophe(c) for c in collections_payload}
        for item in records:
            if not isinstance(item, dict):
                continue
            coll = display_value(item.get("collectionTitle")) or display_value(item.get("collectionName"))
            if coll and _norm_apostrophe(coll) not in target_norms:
                continue
            name = display_value(item.get("modelTitle")) or display_value(item.get("modelName"))
            if not name or name in seen:
                continue
            thumb_key = (
                item.get("modelStickerThumbnailKey")
                or item.get("stickerThumbnailKey")
                or item.get("symbolStickerThumbnailKey")
                or item.get("thumbnailKey")
                or item.get("imageKey")
            )
            photo_url = _absolute_url(thumb_key, base_url=MRKT_CDN_BASE_URL) if thumb_key else None
            rarity = item.get("rarityPerMille")
            seen[name] = {"name": name, "photo_url": photo_url, "rarity_per_mille": rarity}
        return sorted(seen.values(), key=lambda x: x["name"].casefold())

    async def catalog_backdrops(self, collection: str) -> list[dict]:
        collections_payload = [collection]
        if "'" in collection or "’" in collection or "‘" in collection:
            curly = collection.replace("'", "’")
            straight = collection.replace("’", "'").replace("‘", "'")
            collections_payload = list(dict.fromkeys([collection, curly, straight]))

        result = await self._request_with_token_refresh(
            "POST",
            f"{self.settings.mrkt_base_url}/api/v1/gifts/backdrops",
            json={"collections": collections_payload},
            use_proxy=False,
        )
        records = result if isinstance(result, list) else result.get("backdrops", [])
        seen: dict[str, dict] = {}
        target_norms = {_norm_apostrophe(c) for c in collections_payload}
        for item in records:
            if not isinstance(item, dict):
                continue
            coll = display_value(item.get("collectionTitle")) or display_value(item.get("collectionName"))
            if coll and _norm_apostrophe(coll) not in target_norms:
                continue
            name = display_value(item.get("backdropName")) or display_value(item.get("name"))
            if not name or name in seen:
                continue
            center_color = item.get("colorsCenterColor")
            edge_color = item.get("colorsEdgeColor")
            center_hex = f"#{int(center_color) & 0xFFFFFF:06x}" if center_color is not None else None
            edge_hex = f"#{int(edge_color) & 0xFFFFFF:06x}" if edge_color is not None else None
            seen[name] = {
                "name": name,
                "center_color": center_hex,
                "edge_color": edge_hex,
            }
        return sorted(seen.values(), key=lambda x: x["name"].casefold())

    async def sales(self, collection: str, model: str, *, count: int = 30) -> list[Sale]:
        payload = {
            "count": count,
            "cursor": "",
            "collectionNames": [collection],
            "modelNames": [model],
            "backdropNames": [],
            "type": ["Sale"],
            "ordering": "Latest",
            "lowToHigh": False,
        }
        result = await self._request_with_token_refresh("POST", f"{self.settings.mrkt_base_url}/api/v1/feed", json=payload)
        sales: list[Sale] = []
        for event in result.get("items", []):
            gift = event.get("gift") or {}
            price = nano_to_ton(event.get("amount"))
            if price <= 0:
                continue
            gift_id = str(gift.get("id") or "")
            gift_name = str(gift.get("name") or "")
            sales.append(
                Sale(
                    market=Market.MRKT,
                    sale_id=str(event.get("id") or ""),
                    occurred_at=str(event.get("date") or ""),
                    price_ton=price,
                    collection=str(gift.get("collectionName") or collection),
                    model=str(gift.get("modelName") or model),
                    symbol=str(gift.get("symbolName") or "unknown"),
                    backdrop=str(gift.get("backdropName") or "unknown"),
                    gift_number=number(gift.get("number")),
                    model_rarity=number(gift.get("modelRarityPerMille")) / 10,
                    symbol_rarity=number(gift.get("symbolRarityPerMille")) / 10,
                    backdrop_rarity=number(gift.get("backdropRarityPerMille")) / 10,
                    gift_link=f"https://t.me/nft/{gift_name}" if gift_name else None,
                    market_link=f"https://t.me/mrkt/app?startapp={gift_id}" if gift_id else None,
                )
            )
        return sales

    async def _request_with_token_refresh(self, method: str, url: str, *, use_proxy: bool = True, **kwargs: Any) -> Any:
        try:
            return await self._request(method, url, headers=await self.headers(), use_proxy=use_proxy, **kwargs)
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code != 401:
                raise
            await self._token_provider.refresh_token()
            return await self._request(method, url, headers=await self.headers(), use_proxy=use_proxy, **kwargs)

    @staticmethod
    def parse_listing(raw: dict[str, Any]) -> GiftListing | None:
        price = nano_to_ton(raw.get("salePrice"))
        if price <= 0:
            return None
        gift_id = str(raw.get("id") or "")
        gift_name = display_value(raw.get("name"))
        collection = display_value(raw.get("collectionName"))
        if not collection:
            return None
        model = display_value(raw.get("modelName"))
        gift_number = number(raw.get("number"))
        title = display_value(raw.get("title")) or (
            f"{collection} #{int(gift_number)}" if gift_number else collection
        )
        return GiftListing(
            market=Market.MRKT,
            listing_id=gift_id,
            collection=collection,
            title=title,
            current_price_ton=price,
            model=model,
            symbol=display_value(raw.get("symbolName")),
            backdrop=display_value(raw.get("backdropName")),
            market_link=f"https://t.me/mrkt/app?startapp={gift_id}",
            tg_link=f"https://t.me/nft/{gift_name}" if gift_name else None,
            gift_number=gift_number,
            model_rarity=number(raw.get("modelRarityPerMille")) / 10,
            symbol_rarity=number(raw.get("symbolRarityPerMille")) / 10,
            backdrop_rarity=number(raw.get("backdropRarityPerMille")) / 10,
            floor_model_ton=nano_to_ton(raw.get("floorPriceNanoTons")) or None,
            photo_url=_absolute_url(raw.get("modelStickerThumbnailKey") or raw.get("symbolStickerThumbnailKey"), base_url=MRKT_CDN_BASE_URL),
            raw=raw,
        )
