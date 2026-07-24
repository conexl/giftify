import tempfile
import unittest

from giftify.domain import GiftListing, GiftSnapshot, Market
from giftify.purchases import DryRunPurchaseExecutor, PurchaseStatus
from giftify.rules import NewRule
from giftify.storage import SQLiteStore
from giftify.worker import AutoBuyWorker


class FakeCollector:
    async def collect_for_rules(self, rules, *, limit_per_query):
        return await self.collect(None)

    async def collect(self, request):
        return [
            GiftSnapshot(
                listing=GiftListing(
                    market=Market.MRKT,
                    listing_id="gift-1",
                    collection="Cool Gift",
                    title="Cool Gift #1",
                    current_price_ton=4,
                    model="Dragon",
                    symbol="Star",
                    backdrop="Blue",
                    market_link="https://example.test",
                ),
                sales=[],
            )
        ]


class TwoMatchingGiftsCollector:
    async def collect_for_rules(self, rules, *, limit_per_query):
        return await self.collect(None)

    async def collect(self, request):
        return [
            GiftSnapshot(
                listing=GiftListing(
                    market=Market.MRKT,
                    listing_id=listing_id,
                    collection="Cool Gift",
                    title=f"Cool Gift #{index}",
                    current_price_ton=3,
                    model="Dragon",
                    symbol="Star",
                    backdrop="Blue",
                    market_link="https://example.test",
                ),
                sales=[],
            )
            for index, listing_id in enumerate(("gift-1", "gift-2"), 1)
        ]


class WorkerTest(unittest.IsolatedAsyncioTestCase):
    async def test_poll_once_scans_market_even_without_active_rules(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store = SQLiteStore(f"{tmpdir}/giftify.sqlite3")
            store.set_bot_paused(False)
            worker = AutoBuyWorker(FakeCollector(), store, DryRunPurchaseExecutor())

            report = await worker.poll_once(limit_per_market=10)

            self.assertEqual(report.listings_seen, 1)
            self.assertEqual(report.matches_seen, 0)
            self.assertEqual(report.attempts_recorded, 0)
            self.assertEqual(len(store.list_listing_history()), 1)
            store.close()

    async def test_poll_once_skips_all_market_activity_when_emergency_stop_is_enabled(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store = SQLiteStore(f"{tmpdir}/giftify.sqlite3")
            store.create_rule(NewRule(user_id=1, collection="Cool Gift", max_price_ton=5))
            store.set_bot_paused(True)
            worker = AutoBuyWorker(FakeCollector(), store, DryRunPurchaseExecutor())

            report = await worker.poll_once(limit_per_market=10)

            self.assertEqual(report.listings_seen, 0)
            self.assertEqual(report.matches_seen, 0)
            self.assertEqual(report.attempts_recorded, 0)
            self.assertEqual(store.list_attempts(), [])
            store.close()

    async def test_poll_once_records_dry_run_attempt_and_is_idempotent(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store = SQLiteStore(f"{tmpdir}/giftify.sqlite3")
            store.create_rule(NewRule(user_id=1, collection="Cool Gift", max_price_ton=5))
            store.set_bot_paused(False)
            worker = AutoBuyWorker(FakeCollector(), store, DryRunPurchaseExecutor())

            first = await worker.poll_once(limit_per_market=10)
            second = await worker.poll_once(limit_per_market=10)

            self.assertEqual(first.listings_seen, 1)
            self.assertEqual(first.matches_seen, 1)
            self.assertEqual(first.attempts_recorded, 1)
            self.assertEqual(second.matches_seen, 1)
            self.assertEqual(second.attempts_recorded, 0)
            self.assertEqual(len(store.list_attempts()), 1)
            self.assertEqual(len(store.list_catalog()), 1)
            self.assertEqual(len(store.list_listing_history(collection="Cool Gift")), 1)
            store.close()

    async def test_poll_once_does_not_exceed_spend_limit_with_multiple_matches(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store = SQLiteStore(f"{tmpdir}/giftify.sqlite3")
            store.create_rule(NewRule(user_id=1, collection="Cool Gift", max_price_ton=5, max_spend_ton=5))
            store.set_bot_paused(False)
            worker = AutoBuyWorker(TwoMatchingGiftsCollector(), store, DryRunPurchaseExecutor())

            report = await worker.poll_once(limit_per_market=10)

            self.assertEqual(report.matches_seen, 2)
            self.assertEqual(report.attempts_recorded, 1)
            self.assertEqual(len(store.list_attempts()), 1)
            store.close()

    async def test_poll_once_records_executor_failure_and_does_not_retry_listing(self):
        class RaisingExecutor:
            calls = 0

            async def buy(self, rule, listing, *, idempotency_key):
                self.calls += 1
                raise RuntimeError("unexpected response")

        with tempfile.TemporaryDirectory() as tmpdir:
            store = SQLiteStore(f"{tmpdir}/giftify.sqlite3")
            store.create_rule(NewRule(user_id=1, collection="Cool Gift", max_price_ton=5))
            store.set_bot_paused(False)
            executor = RaisingExecutor()
            worker = AutoBuyWorker(FakeCollector(), store, executor)

            first = await worker.poll_once(limit_per_market=10)
            second = await worker.poll_once(limit_per_market=10)

            self.assertEqual(first.attempts_recorded, 1)
            self.assertEqual(second.attempts_recorded, 0)
            self.assertEqual(executor.calls, 1)
            self.assertEqual(store.list_attempts()[0].status, PurchaseStatus.FAILED)
            self.assertEqual(worker.last_purchase_error.status, PurchaseStatus.FAILED)
            store.close()


if __name__ == "__main__":
    unittest.main()
