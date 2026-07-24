import json
import tempfile
import unittest
from pathlib import Path

from giftify.catalog_seed import seed_catalog_from_snapshots
from giftify.storage import SQLiteStore


class CatalogSeedTest(unittest.TestCase):
    def test_seed_catalog_from_kalyvan_snapshot_shape(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "listings-1.json").write_text(
                json.dumps(
                    {
                        "listings": [
                            {
                                "source": "mrkt",
                                "listing_id": "gift-1",
                                "current_price_ton": 2.5,
                                "collection": "Lol Pop",
                                "model": "Cappuccino",
                                "symbol": "Flower",
                                "backdrop": "Lemongrass",
                                "link": "https://example.test",
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )
            store = SQLiteStore(":memory:")

            imported = seed_catalog_from_snapshots(store, str(root))

            self.assertEqual(imported, 1)
            catalog = store.list_catalog()
            self.assertEqual(catalog[0].collection, "Lol Pop")
            self.assertEqual(catalog[0].model, "Cappuccino")
            self.assertEqual(catalog[0].backdrop, "Lemongrass")
            store.close()


if __name__ == "__main__":
    unittest.main()
