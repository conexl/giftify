from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass

from .clients import MrktClient, PortalsClient, TunnelClient
from .domain import GiftListing, GiftSnapshot, Market, Sale
from .rules import AutoBuyRule

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class CollectionRequest:
    markets: tuple[Market, ...] = (Market.MRKT, Market.PORTALS, Market.TUNNEL)
    limit_per_market: int = 20
    include_sales: bool = True
    sales_limit: int = 30
    max_price_ton: float | None = None


class GiftCollector:
    def __init__(self, mrkt: MrktClient, portals: PortalsClient, tunnel: TunnelClient | None = None) -> None:
        self._mrkt = mrkt
        self._portals = portals
        self._tunnel = tunnel

    async def close(self) -> None:
        tasks = [self._mrkt.close(), self._portals.close()]
        if self._tunnel is not None:
            tasks.append(self._tunnel.close())
        await asyncio.gather(*tasks)

    async def collect(self, request: CollectionRequest) -> list[GiftSnapshot]:
        results = await asyncio.gather(*self._listing_tasks(request), return_exceptions=True)
        listings: list[GiftListing] = []
        for result in results:
            if isinstance(result, Exception):
                logger.warning("market listing fetch failed: %s", result)
                continue
            listings.extend(result)
        if not request.include_sales:
            return [GiftSnapshot(listing=listing, sales=[]) for listing in listings]

        sale_batches = await asyncio.gather(
            *(self._sales_for(listing, request.sales_limit) for listing in listings),
            return_exceptions=True,
        )
        normalized_sales: list[list[Sale]] = []
        for batch in sale_batches:
            if isinstance(batch, Exception):
                logger.warning("sales fetch failed: %s", batch)
                normalized_sales.append([])
            else:
                normalized_sales.append(batch)
        return [GiftSnapshot(listing=listing, sales=sales) for listing, sales in zip(listings, normalized_sales, strict=True)]

    async def collect_for_rules(self, rules: list[AutoBuyRule], *, limit_per_query: int = 20) -> list[GiftSnapshot]:
        enabled_rules = [rule for rule in rules if rule.enabled]
        if not enabled_rules:
            return []

        query_limits = self._targeted_query_limits(enabled_rules)
        tasks = []
        has_tunnel = False
        tunnel_max_price = 0.0

        for (market, collection, model, backdrop), max_price_ton in query_limits.items():
            if market == Market.TUNNEL:
                has_tunnel = True
                tunnel_max_price = max(tunnel_max_price, max_price_ton)
            else:
                tasks.append(
                    self._listings_for_target(
                        market=market,
                        collection=collection,
                        model=model,
                        backdrop=backdrop,
                        max_price_ton=max_price_ton,
                        limit=limit_per_query,
                    )
                )

        if has_tunnel and self._tunnel is not None:
            tasks.append(self._tunnel.listings(limit=limit_per_query, max_price_ton=tunnel_max_price))

        results = await asyncio.gather(*tasks, return_exceptions=True)
        deduped: dict[tuple[Market, str], GiftListing] = {}
        for batch in results:
            if isinstance(batch, Exception):
                logger.warning("targeted listing fetch failed: %s", batch)
                continue
            for listing in batch:
                deduped[(listing.market, listing.listing_id)] = listing
        return [GiftSnapshot(listing=listing, sales=[]) for listing in deduped.values()]

    def _listing_tasks(self, request: CollectionRequest):
        if Market.MRKT in request.markets:
            yield self._mrkt.listings(count=request.limit_per_market, max_price_ton=request.max_price_ton)
        if Market.PORTALS in request.markets:
            yield self._portals.listings(limit=request.limit_per_market, max_price_ton=request.max_price_ton)
        if Market.TUNNEL in request.markets and self._tunnel is not None:
            yield self._tunnel.listings(limit=request.limit_per_market, max_price_ton=request.max_price_ton)

    def _targeted_query_limits(self, rules: list[AutoBuyRule]) -> dict[tuple[Market, str, str | None, str | None], float]:
        query_limits: dict[tuple[Market, str, str | None, str | None], float] = {}
        for rule in rules:
            if not rule.enabled:
                continue
            markets = (rule.market,) if rule.market else (Market.MRKT, Market.PORTALS, Market.TUNNEL)
            for market in markets:
                key = (market, rule.collection, rule.model, rule.backdrop)
                query_limits[key] = max(query_limits.get(key, 0), rule.max_price_ton)
        return query_limits

    async def _listings_for_target(
        self,
        *,
        market: Market,
        collection: str,
        model: str | None,
        backdrop: str | None,
        max_price_ton: float,
        limit: int,
    ) -> list[GiftListing]:
        if market == Market.MRKT:
            return await self._mrkt.listings(
                count=limit,
                collection_names=[collection],
                model_names=[model] if model else None,
                backdrop_names=[backdrop] if backdrop else None,
                max_price_ton=max_price_ton,
            )
        if market == Market.TUNNEL:
            if self._tunnel is None:
                return []
            return await self._tunnel.listings(
                limit=limit,
                max_price_ton=max_price_ton,
                search=None,
            )
        return await self._portals.listings(
            limit=limit,
            collection_ids=[collection],
            model=model,
            backdrop=backdrop,
            max_price_ton=max_price_ton,
        )

    async def _sales_for(self, listing: GiftListing, limit: int) -> list[Sale]:
        if not listing.collection or not listing.model:
            return []
        if listing.market == Market.MRKT:
            return await self._mrkt.sales(listing.collection, listing.model, count=limit)
        if listing.market == Market.TUNNEL:
            if self._tunnel is None:
                return []
            return await self._tunnel.sales(listing.collection, listing.model, count=limit)
        return await self._portals.sales(listing.collection, listing.model, count=limit)
