import unittest

from giftify.api import _is_public_catalog_value
from giftify.domain import GiftListing, Market
from giftify.storage import SQLiteStore


class CatalogShapeTest(unittest.TestCase):
    def test_catalog_can_be_grouped_for_mini_app_filters(self):
        store = SQLiteStore(":memory:")
        store.upsert_catalog(
            [
                GiftListing(
                    market=Market.MRKT,
                    listing_id="1",
                    collection="Cool Gift",
                    title="Cool Gift #1",
                    current_price_ton=2,
                    model="Dragon",
                    symbol="Star",
                    backdrop="Blue",
                    market_link="https://example.test/1",
                ),
                GiftListing(
                    market=Market.PORTALS,
                    listing_id="2",
                    collection="Cool Gift",
                    title="Cool Gift #2",
                    current_price_ton=3,
                    model="Wizard",
                    symbol="Moon",
                    backdrop="Red",
                    market_link="https://example.test/2",
                ),
            ]
        )

        options = store.list_catalog()
        models = sorted({option.model for option in options if option.collection == "Cool Gift"})
        backdrops = sorted({option.backdrop for option in options if option.collection == "Cool Gift"})

        self.assertEqual(models, ["Dragon", "Wizard"])
        self.assertEqual(backdrops, ["Blue", "Red"])
        store.close()

    def test_portals_collection_ids_are_not_catalog_filter_names(self):
        self.assertFalse(_is_public_catalog_value("019c1ce5-ef20-7763-9717-ee7fd48bfe46"))
        self.assertFalse(_is_public_catalog_value("123456"))
        self.assertTrue(_is_public_catalog_value("Cool Gift"))
        self.assertTrue(_is_public_catalog_value(None))

    def test_identifier_like_titles_are_not_public_display_values(self):
        self.assertFalse(_is_public_catalog_value("f93efa5f-5da9-4561-b561-fcc7839b4c25"))


if __name__ == "__main__":
    unittest.main()
