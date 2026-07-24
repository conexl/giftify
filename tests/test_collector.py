import unittest

from giftify.collector import CollectionRequest, GiftCollector
from giftify.domain import GiftListing, Market, Sale
from giftify.rules import AutoBuyRule


class FakeMrkt:
    def __init__(self):
        self.calls = []

    async def listings(self, **kwargs):
        self.calls.append(kwargs)
        return [
            GiftListing(
                market=Market.MRKT,
                listing_id="m1",
                collection="Cool Gift",
                title="Cool Gift #1",
                current_price_ton=1.0,
                model="Dragon",
                symbol="Star",
                backdrop="Blue",
                market_link="https://t.me/mrkt/app?startapp=m1",
            )
        ]

    async def sales(self, collection, model, *, count):
        return [
            Sale(
                market=Market.MRKT,
                sale_id="s1",
                occurred_at="2026-07-13T00:00:00Z",
                price_ton=2.0,
                collection=collection,
                model=model,
                symbol="Star",
                backdrop="Blue",
            )
        ]


class FakePortals:
    def __init__(self):
        self.calls = []

    async def listings(self, **kwargs):
        self.calls.append(kwargs)
        return [
            GiftListing(
                market=Market.PORTALS,
                listing_id="p1",
                collection="collection-1",
                title="Portal Gift",
                current_price_ton=3.0,
                model="Wizard",
                symbol="Moon",
                backdrop="Red",
                market_link="https://t.me/portals_market_bot/market?startapp=gift_p1",
            )
        ]

    async def sales(self, collection, model, *, count):
        return []


class CollectorTest(unittest.IsolatedAsyncioTestCase):
    async def test_collects_listings_and_attaches_sales(self):
        collector = GiftCollector(FakeMrkt(), FakePortals())

        snapshots = await collector.collect(CollectionRequest(limit_per_market=5, include_sales=True))

        self.assertEqual(len(snapshots), 2)
        self.assertEqual(snapshots[0].listing.market, Market.MRKT)
        self.assertEqual(snapshots[0].sales[0].price_ton, 2.0)
        self.assertEqual(snapshots[1].listing.market, Market.PORTALS)
        self.assertEqual(snapshots[1].sales, [])

    async def test_can_collect_without_sales(self):
        collector = GiftCollector(FakeMrkt(), FakePortals())

        snapshots = await collector.collect(CollectionRequest(include_sales=False))

        self.assertEqual(len(snapshots), 2)
        self.assertEqual([snapshot.sales for snapshot in snapshots], [[], []])

    async def test_collect_for_rules_pushes_filters_to_market_clients(self):
        mrkt = FakeMrkt()
        portals = FakePortals()
        collector = GiftCollector(mrkt, portals)

        snapshots = await collector.collect_for_rules(
            [
                AutoBuyRule(
                    id=1,
                    user_id=1,
                    market=None,
                    collection="Cool Gift",
                    model="Dragon",
                    backdrop="Blue",
                    max_price_ton=5,
                )
            ],
            limit_per_query=7,
        )

        self.assertEqual(len(snapshots), 2)
        self.assertEqual(mrkt.calls[0]["count"], 7)
        self.assertEqual(mrkt.calls[0]["collection_names"], ["Cool Gift"])
        self.assertEqual(mrkt.calls[0]["model_names"], ["Dragon"])
        self.assertEqual(mrkt.calls[0]["backdrop_names"], ["Blue"])
        self.assertEqual(mrkt.calls[0]["max_price_ton"], 5)
        self.assertEqual(portals.calls[0]["limit"], 7)
        self.assertEqual(portals.calls[0]["collection_ids"], ["Cool Gift"])
        self.assertEqual(portals.calls[0]["model"], "Dragon")
        self.assertEqual(portals.calls[0]["backdrop"], "Blue")
        self.assertEqual(portals.calls[0]["max_price_ton"], 5)


if __name__ == "__main__":
    unittest.main()
