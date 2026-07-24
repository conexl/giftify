import unittest
from types import SimpleNamespace

from giftify.clients import MrktClient, PortalsClient, TunnelClient
from giftify.domain import Market


class MrktParsingTest(unittest.TestCase):
    def test_parse_listing_normalizes_nano_tons_and_characteristics(self):
        listing = MrktClient.parse_listing(
            {
                "id": "gift-1",
                "name": "CoolGift-42",
                "title": "Cool Gift #42",
                "salePrice": 12_500_000_000,
                "collectionName": "Cool Gift",
                "modelName": "Dragon",
                "symbolName": "Star",
                "backdropName": "Blue",
                "modelStickerThumbnailKey": "gifts/stickers/thumbnails/cool.webp",
                "number": 42,
                "modelRarityPerMille": 15,
                "symbolRarityPerMille": 200,
                "backdropRarityPerMille": 100,
            }
        )

        self.assertIsNotNone(listing)
        assert listing is not None
        self.assertEqual(listing.market, Market.MRKT)
        self.assertEqual(listing.current_price_ton, 12.5)
        self.assertEqual(listing.model, "Dragon")
        self.assertEqual(listing.backdrop, "Blue")
        self.assertEqual(listing.model_rarity, 1.5)
        self.assertEqual(listing.tg_link, "https://t.me/nft/CoolGift-42")
        self.assertEqual(listing.photo_url, "https://cdn.tgmrkt.io/gifts/stickers/thumbnails/cool.webp")

    def test_parse_listing_never_uses_uuid_as_a_visible_title(self):
        listing = MrktClient.parse_listing(
            {
                "id": "f93efa5f-5da9-4561-b561-fcc7839b4c25",
                "name": "f93efa5f-5da9-4561-b561-fcc7839b4c25",
                "title": "f93efa5f-5da9-4561-b561-fcc7839b4c25",
                "salePrice": 1_250_000_000,
                "collectionName": "Cool Gift",
                "number": 42,
            }
        )

        assert listing is not None
        self.assertEqual(listing.title, "Cool Gift #42")
        self.assertEqual(listing.collection, "Cool Gift")


class MrktCatalogTest(unittest.IsolatedAsyncioTestCase):
    async def test_reads_human_collection_titles(self):
        client = object.__new__(MrktClient)
        client.settings = SimpleNamespace(mrkt_base_url="https://api.test")

        async def request(*args, **kwargs):
            return [{"name": "Surge Board", "title": "Surge Board"}, {"name": "f93efa5f-5da9-4561-b561-fcc7839b4c25", "title": ""}]

        client._request_with_token_refresh = request

        self.assertEqual(await client.catalog_collections(), [{"name": "Surge Board", "photo_url": None}])

    async def test_reads_models_for_selected_collection(self):
        client = object.__new__(MrktClient)
        client.settings = SimpleNamespace(mrkt_base_url="https://api.test")

        async def request(*args, **kwargs):
            return [
                {"collectionName": "UFC Strike", "modelName": "Gold Adesanya", "modelTitle": "Gold Adesanya"},
                {"collectionName": "Other", "modelName": "Ignored"},
            ]

        client._request_with_token_refresh = request

        self.assertEqual(await client.catalog_models("UFC Strike"), [{"name": "Gold Adesanya", "photo_url": None, "rarity_per_mille": None}])


class PortalsParsingTest(unittest.TestCase):
    def test_parse_listing_normalizes_attributes(self):
        listing = PortalsClient.parse_listing(
            {
                "id": "portal-1",
                "tg_id": "CoolGift-7",
                "name": "Cool Gift",
                "price": "3.75",
                "collection_id": "collection-1",
                "external_collection_number": 7,
                "floor_price": "3.0",
                "attributes": [
                    {"type": "model", "value": "Wizard", "rarity_per_mille": 30},
                    {"type": "symbol", "value": "Moon", "rarity_per_mille": 120},
                    {"type": "backdrop", "value": "Red", "rarity_per_mille": 80},
                ],
            }
        )

        self.assertIsNotNone(listing)
        assert listing is not None
        self.assertEqual(listing.market, Market.PORTALS)
        self.assertEqual(listing.current_price_ton, 3.75)
        self.assertEqual(listing.collection, "Cool Gift")
        self.assertEqual(listing.model, "Wizard")
        self.assertEqual(listing.backdrop, "Red")
        self.assertEqual(listing.floor_gift_ton, 3.0)

    def test_parse_listing_rejects_portals_record_without_a_human_collection_name(self):
        listing = PortalsClient.parse_listing(
            {
                "id": "portal-1",
                "name": "019c1ce5-ef20-7763-9717-ee7fd48bfe46",
                "collection_id": "019c1ce5-ef20-7763-9717-ee7fd48bfe46",
                "price": "3.75",
            }
        )

        self.assertIsNone(listing)


class TunnelParsingTest(unittest.TestCase):
    def test_parse_listing_normalizes_price_and_properties(self):
        from giftify.clients import TunnelClient
        listing = TunnelClient.parse_listing(
            {
                "gift_num": 262,
                "gift_id": 10232372,
                "name": "Scared Cat",
                "model": "Voodoo (4%)",
                "symbol": "Shell (0.2%)",
                "backdrop": "Black (1.5%)",
                "price": 10000,
            }
        )

        self.assertIsNotNone(listing)
        assert listing is not None
        self.assertEqual(listing.market, Market.TUNNEL)
        self.assertEqual(listing.current_price_ton, 10.0)
        self.assertEqual(listing.collection, "Scared Cat")
        self.assertEqual(listing.title, "Scared Cat #262")
        self.assertEqual(listing.model, "Voodoo")
        self.assertEqual(listing.model_rarity, 4.0)
        self.assertEqual(listing.backdrop, "Black")
        self.assertEqual(listing.backdrop_rarity, 1.5)
        self.assertEqual(listing.symbol, "Shell")
        self.assertEqual(listing.symbol_rarity, 0.2)
        self.assertEqual(listing.tg_link, "https://t.me/nft/ScaredCat-262")


if __name__ == "__main__":
    unittest.main()
