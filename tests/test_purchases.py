import json
import unittest

import httpx

from giftify.domain import GiftListing, Market
from giftify.purchases import (
    HttpPurchaseExecutor,
    MarketplacePurchaseRouter,
    MrktPurchaseExecutor,
    PortalsPurchaseExecutor,
    PurchaseStatus,
    TunnelPurchaseExecutor,
)
from giftify.rules import AutoBuyRule


def listing(price=4.0, market=Market.MRKT):
    return GiftListing(
        market=market,
        listing_id="gift-1",
        collection="Cool Gift",
        title="Cool Gift #1",
        current_price_ton=price,
        model="Dragon",
        symbol="Star",
        backdrop="Blue",
        market_link="https://example.test",
    )



class HttpPurchaseExecutorTest(unittest.IsolatedAsyncioTestCase):
    async def test_does_not_call_route_when_price_exceeds_rule_maximum(self):
        called = False

        async def handler(request):
            nonlocal called
            called = True
            return httpx.Response(200, json={"status": "success"})

        executor = HttpPurchaseExecutor("https://buy.test", transport=httpx.MockTransport(handler))
        rule = AutoBuyRule(id=1, user_id=1, collection="Cool Gift", max_price_ton=3.0)

        result = await executor.buy(rule, listing(price=4.0), idempotency_key="1:mrkt:gift-1")

        self.assertFalse(called)
        self.assertEqual(result.status, PurchaseStatus.PRICE_CHANGED)

    async def test_maps_successful_purchase_route_response(self):
        async def handler(request):
            self.assertEqual(request.url, httpx.URL("https://buy.test"))
            return httpx.Response(200, json={"status": "success", "message": "bought", "purchase_id": "p1"})

        executor = HttpPurchaseExecutor("https://buy.test", transport=httpx.MockTransport(handler))
        rule = AutoBuyRule(id=1, user_id=1, collection="Cool Gift", max_price_ton=5.0)

        result = await executor.buy(rule, listing(), idempotency_key="1:mrkt:gift-1")

        self.assertEqual(result.status, PurchaseStatus.SUCCESS)
        self.assertEqual(result.message, "bought")
        self.assertEqual(result.external_purchase_id, "p1")


class MrktPurchaseExecutorTest(unittest.IsolatedAsyncioTestCase):
    async def test_uses_mrkt_contract_with_exact_nano_price_and_idempotency_key(self):
        class TokenProvider:
            async def get_token(self): return "test-token"
            async def refresh_token(self): return "test-token"

        async def handler(request):
            self.assertEqual(request.url, httpx.URL("https://api.tgmrkt.io/api/v1/gifts/buy"))
            self.assertEqual(request.headers["idempotency-key"], "rule:mrkt:gift-1")
            self.assertEqual(json.loads(request.content), {"ids": ["gift-1"], "prices": {"gift-1": 4_123_456_789}})
            return httpx.Response(200, json={"id": "order-1", "message": "bought"})

        executor = MrktPurchaseExecutor(
            "https://api.tgmrkt.io", TokenProvider(), transport=httpx.MockTransport(handler)
        )
        rule = AutoBuyRule(id=1, user_id=1, collection="Cool Gift", max_price_ton=5.0)

        result = await executor.buy(rule, listing(price=4.123456789), idempotency_key="rule:mrkt:gift-1")

        self.assertEqual(result.status, PurchaseStatus.SUCCESS)
        self.assertEqual(result.external_purchase_id, "order-1")

    async def test_accepts_mrkt_batch_response(self):
        class TokenProvider:
            async def get_token(self): return "test-token"
            async def refresh_token(self): return "test-token"

        async def handler(request):
            return httpx.Response(200, json=[{"id": "order-1", "message": "bought"}])

        executor = MrktPurchaseExecutor(
            "https://api.tgmrkt.io", TokenProvider(), transport=httpx.MockTransport(handler)
        )
        rule = AutoBuyRule(id=1, user_id=1, collection="Cool Gift", max_price_ton=5.0)

        result = await executor.buy(rule, listing(), idempotency_key="rule:mrkt:gift-1")

        self.assertEqual(result.status, PurchaseStatus.SUCCESS)
        self.assertEqual(result.external_purchase_id, "order-1")

    async def test_accepts_the_confirmed_mrkt_user_gift_response(self):
        class TokenProvider:
            async def get_token(self): return "test-token"
            async def refresh_token(self): return "test-token"

        async def handler(request):
            return httpx.Response(200, json=[{"type": "gift", "userGift": {"id": "gift-1", "isMine": True}}])

        executor = MrktPurchaseExecutor(
            "https://api.tgmrkt.io", TokenProvider(), transport=httpx.MockTransport(handler)
        )
        rule = AutoBuyRule(id=1, user_id=1, collection="Cool Gift", max_price_ton=5.0)

        result = await executor.buy(rule, listing(), idempotency_key="rule:mrkt:gift-1")

        self.assertEqual(result.status, PurchaseStatus.SUCCESS)
        self.assertEqual(result.external_purchase_id, "gift-1")

    async def test_marks_empty_mrkt_batch_response_as_unconfirmed_price(self):
        class TokenProvider:
            async def get_token(self): return "test-token"
            async def refresh_token(self): return "test-token"

        async def handler(request):
            return httpx.Response(200, json=[])

        executor = MrktPurchaseExecutor(
            "https://api.tgmrkt.io", TokenProvider(), transport=httpx.MockTransport(handler)
        )
        rule = AutoBuyRule(id=1, user_id=1, collection="Cool Gift", max_price_ton=5.0)

        result = await executor.buy(rule, listing(), idempotency_key="rule:mrkt:gift-1")

        self.assertEqual(result.status, PurchaseStatus.PRICE_CHANGED)


class PortalsPurchaseExecutorTest(unittest.IsolatedAsyncioTestCase):
    async def test_uses_portals_nft_buy_contract_and_tma_header(self):
        class TokenProvider:
            async def get_token(self): return "tma query_id=123&user=test"
            async def refresh_token(self): return "tma query_id=123&user=test"

        async def handler(request):
            self.assertEqual(request.url, httpx.URL("https://portal-market.com/api/nfts"))
            self.assertEqual(request.headers["authorization"], "tma query_id=123&user=test")
            self.assertEqual(request.headers["x-request-id"], "rule:portals:p-nft-1")
            self.assertEqual(
                json.loads(request.content),
                {"nft_details": [{"id": "p-nft-1", "price": "2.56"}]},
            )
            return httpx.Response(200, json={"nft_details": [{"id": "p-nft-1", "price": "2.56"}]})

        executor = PortalsPurchaseExecutor(
            "https://portal-market.com", TokenProvider(), transport=httpx.MockTransport(handler)
        )
        rule = AutoBuyRule(id=1, user_id=1, collection="Cool Gift", max_price_ton=3.0)

        portals_listing = GiftListing(
            market=Market.PORTALS,
            listing_id="p-nft-1",
            collection="Cool Gift",
            title="Cool Gift #1",
            current_price_ton=2.56,
            model="Dragon",
            symbol="Star",
            backdrop="Blue",
            market_link="https://example.test",
        )
        result = await executor.buy(rule, portals_listing, idempotency_key="rule:portals:p-nft-1")

        self.assertEqual(result.status, PurchaseStatus.SUCCESS)
        self.assertEqual(result.external_purchase_id, "p-nft-1")

    async def test_routes_via_marketplace_purchase_router(self):
        class TokenProvider:
            async def get_token(self): return "token"
            async def refresh_token(self): return "token"

        async def handler(request):
            return httpx.Response(200, json={"nft_details": [{"id": "p-nft-1", "price": "2.56"}]})

        portals_exec = PortalsPurchaseExecutor(
            "https://portal-market.com", TokenProvider(), transport=httpx.MockTransport(handler)
        )
        router = MarketplacePurchaseRouter({Market.PORTALS: portals_exec})
        rule = AutoBuyRule(id=1, user_id=1, collection="Cool Gift", max_price_ton=3.0)

        portals_listing = listing(price=2.56, market=Market.PORTALS)
        result = await router.buy(rule, portals_listing, idempotency_key="rule:portals:p-nft-1")

        self.assertEqual(result.status, PurchaseStatus.SUCCESS)


class TunnelPurchaseExecutorTest(unittest.IsolatedAsyncioTestCase):
    async def test_uses_tunnel_buy_gift_endpoint_and_headers(self):
        class TokenProvider:
            async def get_token(self): return "tunnel-auth-data"
            async def refresh_token(self): return "tunnel-auth-data"

        async def handler(request):
            self.assertEqual(request.url, httpx.URL("https://gifts3.tonnel.network/api/buyGift/10335578"))
            body = json.loads(request.content)
            self.assertEqual(body["authData"], "tunnel-auth-data")
            self.assertEqual(body["asset"], "TON")
            self.assertEqual(body["price"], 2.58)
            self.assertIn("timestamp", body)
            self.assertIn("wtf", body)
            return httpx.Response(200, json={"status": "success", "tx": "tx-tunnel-123"})

        executor = TunnelPurchaseExecutor(
            "https://gifts3.tonnel.network", TokenProvider(), transport=httpx.MockTransport(handler)
        )
        rule = AutoBuyRule(id=1, user_id=1, collection="Cool Gift", max_price_ton=3.0)

        tunnel_listing = GiftListing(
            market=Market.TUNNEL,
            listing_id="10335578",
            collection="Cool Gift",
            title="Cool Gift #10335578",
            current_price_ton=2.58,
            model="Dragon",
            symbol="Star",
            backdrop="Blue",
            market_link="https://t.me/tonnel_network_bot/gifts?startapp=10335578",
        )
        result = await executor.buy(rule, tunnel_listing, idempotency_key="rule:tunnel:10335578")

        self.assertEqual(result.status, PurchaseStatus.SUCCESS)
        self.assertEqual(result.external_purchase_id, "tx-tunnel-123")

    async def test_handles_tunnel_error_response(self):
        class TokenProvider:
            async def get_token(self): return "bad-auth"
            async def refresh_token(self): return "bad-auth"

        async def handler(request):
            return httpx.Response(200, json={"status": "error", "message": "Invalid auth data"})

        executor = TunnelPurchaseExecutor(
            "https://gifts3.tonnel.network", TokenProvider(), transport=httpx.MockTransport(handler)
        )
        rule = AutoBuyRule(id=1, user_id=1, collection="Cool Gift", max_price_ton=3.0)

        tunnel_listing = GiftListing(
            market=Market.TUNNEL,
            listing_id="10335578",
            collection="Cool Gift",
            title="Cool Gift #10335578",
            current_price_ton=2.58,
            model="Dragon",
            symbol="Star",
            backdrop="Blue",
            market_link="https://t.me/tonnel_network_bot/gifts?startapp=10335578",
        )
        result = await executor.buy(rule, tunnel_listing, idempotency_key="rule:tunnel:10335578")

        self.assertEqual(result.status, PurchaseStatus.AUTH_FAILED)
        self.assertEqual(result.message, "Invalid auth data")


if __name__ == "__main__":
    unittest.main()

