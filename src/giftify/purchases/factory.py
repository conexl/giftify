from __future__ import annotations

from giftify.config import Settings
from giftify.domain import Market
from .base import (
    DryRunPurchaseExecutor,
    HttpPurchaseExecutor,
    MarketplacePurchaseRouter,
    PurchaseExecutor,
)
from .mrkt import MrktPurchaseExecutor
from .portals import PortalsPurchaseExecutor
from .tunnel import TunnelPurchaseExecutor


def purchase_executor_from_settings(settings: Settings, **kwargs) -> PurchaseExecutor:
    if settings.purchase_mode == "real":
        if not settings.purchase_route_url:
            raise RuntimeError("PURCHASE_ROUTE_URL must be set when PURCHASE_MODE=real")
        return HttpPurchaseExecutor(settings.purchase_route_url, timeout_seconds=settings.market_timeout_seconds)

    token_provider = kwargs.get("token_provider")
    portals_token_provider = kwargs.get("portals_token_provider")
    tunnel_token_provider = kwargs.get("tunnel_token_provider")
    proxy_pool = kwargs.get("proxy_pool")

    if settings.purchase_mode == "portals":
        tp = portals_token_provider or token_provider
        if tp is None:
            raise RuntimeError("token_provider or portals_token_provider is required for PURCHASE_MODE=portals")
        return PortalsPurchaseExecutor(
            settings.portals_base_url,
            tp,
            proxy_pool=proxy_pool,
            timeout_seconds=settings.market_timeout_seconds,
        )

    if settings.purchase_mode == "mrkt":
        if token_provider is None:
            raise RuntimeError("token_provider is required for PURCHASE_MODE=mrkt")
        return MrktPurchaseExecutor(
            settings.mrkt_base_url,
            token_provider,
            proxy_pool=proxy_pool,
            timeout_seconds=settings.market_timeout_seconds,
        )

    if settings.purchase_mode == "tunnel":
        ttp = tunnel_token_provider or token_provider
        if ttp is None:
            raise RuntimeError("token_provider or tunnel_token_provider is required for PURCHASE_MODE=tunnel")
        return TunnelPurchaseExecutor(
            settings.tunnel_base_url,
            ttp,
            proxy_pool=proxy_pool,
            timeout_seconds=settings.market_timeout_seconds,
        )

    if settings.purchase_mode in {"both", "auto", "direct", "all"}:
        executors: dict[Market, PurchaseExecutor] = {}
        if token_provider:
            executors[Market.MRKT] = MrktPurchaseExecutor(
                settings.mrkt_base_url,
                token_provider,
                proxy_pool=proxy_pool,
                timeout_seconds=settings.market_timeout_seconds,
            )
        ptp = portals_token_provider or token_provider
        if ptp:
            executors[Market.PORTALS] = PortalsPurchaseExecutor(
                settings.portals_base_url,
                ptp,
                proxy_pool=proxy_pool,
                timeout_seconds=settings.market_timeout_seconds,
            )
        ttp = tunnel_token_provider or token_provider
        if ttp:
            executors[Market.TUNNEL] = TunnelPurchaseExecutor(
                settings.tunnel_base_url,
                ttp,
                proxy_pool=proxy_pool,
                timeout_seconds=settings.market_timeout_seconds,
            )
        return MarketplacePurchaseRouter(executors)

    return DryRunPurchaseExecutor()
