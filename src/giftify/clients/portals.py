from __future__ import annotations

from typing import Any

from giftify.config import Settings
from giftify.domain import GiftListing, Market, Sale, display_value, is_display_value, number
from giftify.proxies import ProxyPool
from .base import MarketplaceClient, TokenProvider, _absolute_url


class PortalsClient(MarketplaceClient):
    def __init__(self, settings: Settings, proxy_pool: ProxyPool, token_provider: TokenProvider) -> None:
        super().__init__(settings, proxy_pool, Market.PORTALS)
        self._token_provider = token_provider

    async def headers(self) -> dict[str, str]:
        token = await self._token_provider.get_token()
        auth_header = token if token.startswith(("tma ", "Bearer ", "bearer ")) else f"tma {token}"
        return {
            "Authorization": auth_header,
            "Origin": "https://portal-market.com",
            "Referer": "https://portal-market.com/",
            "Accept": "application/json",
        }

    async def listings(
        self,
        *,
        limit: int,
        offset: int = 0,
        collection_ids: list[str] | None = None,
        search: str | None = None,
        model: str | None = None,
        backdrop: str | None = None,
        max_price_ton: float | None = None,
    ) -> list[GiftListing]:
        params: dict[str, Any] = {
            "offset": offset,
            "limit": limit,
            "status": "listed",
            "exclude_bundled": "true",
            "premarket_status": "all",
        }
        if collection_ids:
            uuids = [c for c in collection_ids if "-" in c and len(c) == 36]
            names = [c for c in collection_ids if c not in uuids]
            if uuids:
                params["collection_ids"] = ",".join(uuids)
            if names:
                params["search"] = ",".join(names)
        if search:
            params["search"] = search
        if model:
            params["filter_by_models"] = model

        result = await self._request("GET", f"{self.settings.portals_base_url}/api/nfts/search", headers=await self.headers(), params=params)
        raw_items = result.get("results", []) if isinstance(result, dict) else []
        listings = [listing for item in raw_items if (listing := self.parse_listing(item))]
        if max_price_ton is not None:
            listings = [listing for listing in listings if listing.current_price_ton <= max_price_ton]
        if backdrop:
            listings = [listing for listing in listings if listing.backdrop.casefold() == backdrop.casefold()]
        return listings

    async def sales(self, collection: str, model: str, *, count: int = 100) -> list[Sale]:
        params = {
            "offset": 0,
            "limit": count,
            "collection_ids": collection,
            "filter_by_models": model,
            "action_types": "buy,sell",
        }
        result = await self._request("GET", f"{self.settings.portals_base_url}/api/market/actions/", headers=await self.headers(), params=params)
        raw_actions = result.get("actions", []) if isinstance(result, dict) else []
        sales: list[Sale] = []
        for event in raw_actions:
            if not isinstance(event, dict) or event.get("type") != "purchase":
                continue
            nft = event.get("nft") or {}
            attrs = {attribute.get("type"): attribute for attribute in nft.get("attributes", []) if isinstance(attribute, dict)}
            price = number(event.get("amount"))
            if price <= 0:
                continue
            nft_id = str(nft.get("id") or "")
            tg_id = str(nft.get("tg_id") or "")
            sales.append(
                Sale(
                    market=Market.PORTALS,
                    sale_id=str(event.get("offer_id") or event.get("id") or ""),
                    occurred_at=str(event.get("created_at") or ""),
                    price_ton=price,
                    collection=str(nft.get("name") or collection),
                    model=str((attrs.get("model") or {}).get("value") or model),
                    symbol=str((attrs.get("symbol") or {}).get("value") or "unknown"),
                    backdrop=str((attrs.get("backdrop") or {}).get("value") or "unknown"),
                    gift_number=number(nft.get("external_collection_number")),
                    model_rarity=number((attrs.get("model") or {}).get("rarity_per_mille")) / 10,
                    symbol_rarity=number((attrs.get("symbol") or {}).get("rarity_per_mille")) / 10,
                    backdrop_rarity=number((attrs.get("backdrop") or {}).get("rarity_per_mille")) / 10,
                    gift_link=f"https://t.me/nft/{tg_id}" if tg_id else None,
                    market_link=f"https://t.me/portals_market_bot/market?startapp=gift_{nft_id}" if nft_id else None,
                )
            )
        return sales

    @staticmethod
    def parse_listing(raw: dict[str, Any]) -> GiftListing | None:
        if not isinstance(raw, dict):
            return None
        price = number(raw.get("price"))
        if price <= 0:
            return None
        attrs = {attribute.get("type"): attribute for attribute in raw.get("attributes", []) if isinstance(attribute, dict)}
        gift_id = str(raw.get("id") or "")
        tg_id = str(raw.get("tg_id") or "")
        collection_name = next(
            (
                display_value(raw.get(key))
                for key in ("name", "collection_name", "title")
                if is_display_value(raw.get(key))
            ),
            "",
        )
        if not collection_name:
            return None
        gift_number = number(raw.get("external_collection_number"))
        return GiftListing(
            market=Market.PORTALS,
            listing_id=gift_id,
            collection=collection_name,
            title=f"{collection_name} #{int(gift_number)}" if gift_number else collection_name,
            current_price_ton=price,
            model=display_value((attrs.get("model") or {}).get("value")),
            symbol=display_value((attrs.get("symbol") or {}).get("value")),
            backdrop=display_value((attrs.get("backdrop") or {}).get("value")),
            market_link=f"https://t.me/portals_market_bot/market?startapp=gift_{gift_id}",
            tg_link=f"https://t.me/nft/{tg_id}" if tg_id else None,
            gift_number=gift_number,
            model_rarity=number((attrs.get("model") or {}).get("rarity_per_mille")) / 10,
            symbol_rarity=number((attrs.get("symbol") or {}).get("rarity_per_mille")) / 10,
            backdrop_rarity=number((attrs.get("backdrop") or {}).get("rarity_per_mille")) / 10,
            floor_gift_ton=number(raw.get("floor_price")) or None,
            photo_url=_absolute_url(raw.get("photo_url")),
            raw=raw,
        )
