from __future__ import annotations

import json
import re
from typing import Any

from giftify.config import Settings
from giftify.domain import GiftListing, Market, Sale, display_value, number
from giftify.proxies import ProxyPool
from .base import MarketplaceClient, TokenProvider

RARITY_RE = re.compile(r"^(.*?)\s*\(([\d.]+)%\)$")


class TunnelClient(MarketplaceClient):
    def __init__(self, settings: Settings, proxy_pool: ProxyPool, token_provider: TokenProvider) -> None:
        super().__init__(settings, proxy_pool, Market.TUNNEL)
        self._token_provider = token_provider

    async def headers(self) -> dict[str, str]:
        return {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
            "Accept": "application/json, text/plain, */*",
            "Origin": "https://marketplace.tonnel.network",
            "Referer": "https://marketplace.tonnel.network/",
            "Content-Type": "application/json",
        }

    async def listings(
        self,
        *,
        limit: int = 12,
        page: int = 1,
        max_price_ton: float | None = None,
        search: str | None = None,
    ) -> list[GiftListing]:
        token = await self._token_provider.get_token()

        filter_dict: dict[str, Any] = {
            "price": {"$exists": True},
            "buyer": {"$exists": False},
            "asset": "TON",
        }

        payload: dict[str, Any] = {
            "page": page,
            "limit": limit,
            "sort": '{"price":1,"gift_id":-1}',
            "filter": json.dumps(filter_dict),
            "ref": 0,
            "price_range": None,
            "user_auth": token,
        }
        if search:
            payload["search"] = search

        result = await self._request("POST", f"{self.settings.tunnel_base_url}/api/pageGifts", headers=await self.headers(), json=payload)
        if isinstance(result, list):
            items = result
        elif isinstance(result, dict):
            items = result.get("gifts") or result.get("data") or result.get("results") or []
        else:
            items = []

        listings = [listing for item in items if (listing := self.parse_listing(item))]
        if search:
            search_lower = search.lower()
            listings = [l for l in listings if search_lower in l.collection.lower() or (l.model and search_lower in l.model.lower())]
        if max_price_ton is not None:
            listings = [l for l in listings if l.current_price_ton <= max_price_ton]
        return listings

    async def sales(self, collection: str, model: str, *, count: int = 100) -> list[Sale]:
        return []

    @staticmethod
    def parse_listing(raw: dict[str, Any]) -> GiftListing | None:
        if not isinstance(raw, dict):
            return None
        raw_price = raw.get("price")
        if raw_price is None:
            return None
        price = float(raw_price)
        if price >= 1000.0:
            price = price / 1000.0
        if price <= 0:
            return None

        gift_id = str(raw.get("gift_id") or "")
        collection = display_value(raw.get("name"))
        if not collection:
            return None

        gift_number = number(raw.get("gift_num"))
        title = f"{collection} #{int(gift_number)}" if gift_number else collection

        def parse_prop(val: Any) -> tuple[str, float]:
            val_str = str(val or "").strip()
            if not val_str:
                return "", 0.0
            m = RARITY_RE.match(val_str)
            if m:
                name = m.group(1).strip()
                try:
                    rarity_val = float(m.group(2))
                except ValueError:
                    rarity_val = 0.0
                return name, rarity_val
            return val_str, 0.0

        model_name, model_rarity = parse_prop(raw.get("model"))
        backdrop_name, backdrop_rarity = parse_prop(raw.get("backdrop"))
        symbol_name, symbol_rarity = parse_prop(raw.get("symbol"))

        clean_name = collection.replace(" ", "")
        tg_name = f"{clean_name}-{int(gift_number)}" if gift_number else clean_name
        slug = collection.lower().replace(" ", "").replace("-", "").replace("’", "").replace("'", "")
        photo_url = f"https://nft.fragment.com/gift/{slug}-1.medium.jpg" if slug else None

        return GiftListing(
            market=Market.TUNNEL,
            listing_id=gift_id,
            collection=collection,
            title=title,
            current_price_ton=price,
            model=model_name or None,
            symbol=symbol_name or None,
            backdrop=backdrop_name or None,
            market_link=f"https://t.me/tonnel_network_bot/gifts?startapp={gift_id}",
            tg_link=f"https://t.me/nft/{tg_name}" if tg_name else None,
            gift_number=gift_number,
            model_rarity=model_rarity,
            symbol_rarity=symbol_rarity,
            backdrop_rarity=backdrop_rarity,
            floor_gift_ton=price,
            photo_url=photo_url,
            raw=raw,
        )
