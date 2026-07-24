import tempfile
import unittest

from giftify.domain import GiftListing, Market
from giftify.purchases import PurchaseResult, PurchaseStatus
from giftify.rules import NewRule
from giftify.storage import SQLiteStore


class SQLiteStoreTest(unittest.TestCase):
    def test_persists_emergency_stop_state(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store = SQLiteStore(f"{tmpdir}/giftify.sqlite3")

            self.assertTrue(store.is_bot_paused())
            store.set_bot_paused(False)
            self.assertFalse(store.is_bot_paused())
            store.set_bot_paused(True)
            self.assertTrue(store.is_bot_paused())
            store.close()

    def test_rule_includes_spent_ton_from_saved_matches(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store = SQLiteStore(f"{tmpdir}/giftify.sqlite3")
            rule = store.create_rule(NewRule(user_id=1, collection="Cool Gift", max_price_ton=10, max_spend_ton=20))
            listing = GiftListing(
                market=Market.MRKT,
                listing_id="gift-1",
                collection="Cool Gift",
                title="Cool Gift #1",
                current_price_ton=7,
                model="Dragon",
                symbol="Star",
                backdrop="Blue",
                market_link="https://example.test",
            )
            store.record_attempt(rule, listing, PurchaseResult(PurchaseStatus.DRY_RUN, "saved"), "saved")

            persisted = store.get_rule(rule.id)

            self.assertEqual(persisted.max_spend_ton, 20)
            self.assertEqual(persisted.spent_ton, 7)
            store.close()

    def test_creates_rules_and_prevents_duplicate_attempts(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store = SQLiteStore(f"{tmpdir}/giftify.sqlite3")
            rule = store.create_rule(NewRule(user_id=1, collection="Cool Gift", max_price_ton=5))
            listing = GiftListing(
                market=Market.MRKT,
                listing_id="gift-1",
                collection="Cool Gift",
                title="Cool Gift #1",
                current_price_ton=4,
                model="Dragon",
                symbol="Star",
                backdrop="Blue",
                market_link="https://example.test",
            )
            result = PurchaseResult(PurchaseStatus.DRY_RUN, "would buy")

            self.assertEqual(store.list_rules(), [rule])
            self.assertTrue(store.record_attempt(rule, listing, result, "1:mrkt:gift-1"))
            self.assertFalse(store.record_attempt(rule, listing, result, "1:mrkt:gift-1"))
            self.assertEqual(len(store.list_attempts()), 1)
            store.close()

    def test_deletes_rule_for_user(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store = SQLiteStore(f"{tmpdir}/giftify.sqlite3")
            first = store.create_rule(NewRule(user_id=1, collection="Cool Gift", max_price_ton=5))
            second = store.create_rule(NewRule(user_id=2, collection="Cool Gift", max_price_ton=5))

            self.assertFalse(store.delete_rule(second.id, user_id=1))
            self.assertTrue(store.delete_rule(first.id, user_id=1))

            self.assertEqual(store.list_rules(), [second])
            store.close()

    def test_upserts_catalog_options_from_listings(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store = SQLiteStore(f"{tmpdir}/giftify.sqlite3")
            first = GiftListing(
                market=Market.MRKT,
                listing_id="gift-1",
                collection="Cool Gift",
                title="Cool Gift #1",
                current_price_ton=4,
                model="Dragon",
                symbol="Star",
                backdrop="Blue",
                market_link="https://example.test/1",
            )
            cheaper = GiftListing(
                market=Market.MRKT,
                listing_id="gift-2",
                collection="Cool Gift",
                title="Cool Gift #2",
                current_price_ton=3,
                model="Dragon",
                symbol="Star",
                backdrop="Blue",
                market_link="https://example.test/2",
            )

            store.upsert_catalog([first])
            store.upsert_catalog([cheaper])

            options = store.list_catalog()
            self.assertEqual(len(options), 1)
            self.assertEqual(options[0].collection, "Cool Gift")
            self.assertEqual(options[0].model, "Dragon")
            self.assertEqual(options[0].backdrop, "Blue")
            self.assertEqual(options[0].min_price_ton, 3)
            store.close()

    def test_upserts_and_filters_listing_history(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store = SQLiteStore(f"{tmpdir}/giftify.sqlite3")
            first = GiftListing(
                market=Market.MRKT,
                listing_id="gift-1",
                collection="Cool Gift",
                title="Cool Gift #1",
                current_price_ton=4,
                model="Dragon",
                symbol="Star",
                backdrop="Blue",
                market_link="https://example.test/1",
                photo_url="https://cdn.example.test/gift.webp",
            )
            updated = GiftListing(
                market=Market.MRKT,
                listing_id="gift-1",
                collection="Cool Gift",
                title="Cool Gift #1",
                current_price_ton=3.5,
                model="Dragon",
                symbol="Star",
                backdrop="Blue",
                market_link="https://example.test/1",
                photo_url="https://cdn.example.test/gift.webp",
            )

            store.upsert_listing_history([first])
            store.upsert_listing_history([updated])

            records = store.list_listing_history(collection="Cool Gift", model="Dragon", max_price_ton=4, query="star")
            self.assertEqual(len(records), 1)
            self.assertEqual(records[0].current_price_ton, 3.5)
            self.assertEqual(records[0].photo_url, "https://cdn.example.test/gift.webp")
            self.assertLessEqual(records[0].first_seen_at, records[0].last_seen_at)
            store.close()

    def test_list_purchases_returns_saved_matches_and_successful_attempts(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store = SQLiteStore(f"{tmpdir}/giftify.sqlite3")
            rule = store.create_rule(NewRule(user_id=1, collection="Cool Gift", max_price_ton=5))
            listing = GiftListing(
                market=Market.MRKT,
                listing_id="gift-1",
                collection="Cool Gift",
                title="Cool Gift #1",
                current_price_ton=4,
                model="Dragon",
                symbol="Star",
                backdrop="Blue",
                market_link="https://example.test",
            )

            store.record_attempt(rule, listing, PurchaseResult(PurchaseStatus.DRY_RUN, "would buy"), "dry")
            store.record_attempt(rule, listing, PurchaseResult(PurchaseStatus.SUCCESS, "bought"), "success")

            purchases = store.list_purchases()
            self.assertEqual(len(purchases), 2)
            self.assertEqual({purchase.status for purchase in purchases}, {"dry_run", "success"})
            store.close()

    def test_saved_gifts_include_listing_metadata_for_the_dashboard(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store = SQLiteStore(f"{tmpdir}/giftify.sqlite3")
            rule = store.create_rule(NewRule(user_id=1, collection="Cool Gift", max_price_ton=5))
            listing = GiftListing(
                market=Market.MRKT,
                listing_id="gift-1",
                collection="Cool Gift",
                title="Cool Gift #1",
                current_price_ton=4,
                model="Dragon",
                symbol="Star",
                backdrop="Blue",
                market_link="https://example.test",
                photo_url="https://cdn.example.test/gift.webp",
            )
            store.upsert_listing_history([listing])
            store.record_attempt(rule, listing, PurchaseResult(PurchaseStatus.DRY_RUN, "would save"), "saved")

            gifts = store.list_saved_gifts()

            self.assertEqual(len(gifts), 1)
            self.assertEqual(gifts[0].title, "Cool Gift #1")
            self.assertEqual(gifts[0].photo_url, "https://cdn.example.test/gift.webp")
            self.assertEqual(gifts[0].rule_collection, "Cool Gift")
            self.assertEqual(gifts[0].model_rarity, 0)
            store.close()

    def test_purchased_gifts_exclude_dry_run_matches(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store = SQLiteStore(f"{tmpdir}/giftify.sqlite3")
            rule = store.create_rule(NewRule(user_id=1, collection="Cool Gift", max_price_ton=5))
            listing = GiftListing(
                market=Market.MRKT, listing_id="gift-1", collection="Cool Gift", title="Cool Gift #1",
                current_price_ton=4, model="Dragon", symbol="Star", backdrop="Blue", market_link="https://example.test",
            )
            store.upsert_listing_history([listing])
            store.record_attempt(rule, listing, PurchaseResult(PurchaseStatus.DRY_RUN, "would buy"), "dry")
            store.record_attempt(rule, listing, PurchaseResult(PurchaseStatus.SUCCESS, "bought"), "success")

            gifts = store.list_purchased_gifts()

            self.assertEqual(len(gifts), 1)
            self.assertEqual(gifts[0].title, "Cool Gift #1")

            self.assertTrue(store.archive_saved_gift(gifts[0].id))
            self.assertEqual(len(store.list_purchased_gifts()), 0)
            store.close()


if __name__ == "__main__":
    unittest.main()
