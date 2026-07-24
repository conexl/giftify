from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from time import perf_counter

from .collector import CollectionRequest, GiftCollector
from .notifications import TelegramNotifier
from .purchases import PurchaseExecutor, PurchaseResult, PurchaseStatus
from .rules import RuleMatcher, now_iso
from .storage import SQLiteStore

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class WorkerReport:
    listings_seen: int
    matches_seen: int
    attempts_recorded: int


class AutoBuyWorker:
    def __init__(
        self,
        collector: GiftCollector,
        store: SQLiteStore,
        executor: PurchaseExecutor,
        matcher: RuleMatcher | None = None,
        notifier: TelegramNotifier | None = None,
    ) -> None:
        self._collector = collector
        self._store = store
        self._executor = executor
        self._matcher = matcher or RuleMatcher()
        self._notifier = notifier
        self.last_report: WorkerReport | None = None
        self.last_checked_at: str | None = None
        self.last_error: str | None = None
        self.last_purchase_error: PurchaseResult | None = None

    async def poll_once(self, *, limit_per_market: int = 50) -> WorkerReport:
        logger.debug("poll_once started")
        if self._store.is_bot_paused():
            return self._finish(WorkerReport(listings_seen=0, matches_seen=0, attempts_recorded=0))
        rules = self._store.list_rules(enabled_only=True)
        logger.debug("poll_once active rules: %d", len(rules))
        snapshots = (
            await self._collector.collect_for_rules(rules, limit_per_query=limit_per_market)
            if rules
            else await self._collector.collect(CollectionRequest(limit_per_market=limit_per_market, include_sales=False))
        )
        listings = [snapshot.listing for snapshot in snapshots]
        self._store.upsert_catalog(listings)
        self._store.upsert_listing_history(listings)
        matches = self._matcher.match(rules, listings)

        attempts_recorded = 0
        remaining_spend = {
            rule.id: rule.max_spend_ton - rule.spent_ton
            for rule in rules
            if rule.max_spend_ton is not None
        }
        for match in matches:
            remaining = remaining_spend.get(match.rule.id)
            if remaining is not None and match.listing.current_price_ton > remaining:
                continue
            if self._store.has_final_attempt(match.idempotency_key):
                continue
            try:
                result = await self._executor.buy(match.rule, match.listing, idempotency_key=match.idempotency_key)
            except Exception:
                logger.exception("purchase executor failed for %s", match.idempotency_key)
                result = PurchaseResult(PurchaseStatus.FAILED, "purchase executor failed before a result was returned")
            inserted = self._store.record_attempt(match.rule, match.listing, result, match.idempotency_key)
            if not inserted:
                continue
            attempts_recorded += 1
            if self._notifier is not None:
                self._notifier.publish_attempt(match.listing, result)
            if result.status in {
                PurchaseStatus.INSUFFICIENT_BALANCE,
                PurchaseStatus.AUTH_FAILED,
                PurchaseStatus.RATE_LIMITED,
                PurchaseStatus.FAILED,
            }:
                self.last_purchase_error = result
            if result.status in {PurchaseStatus.SUCCESS, PurchaseStatus.DRY_RUN} and match.rule.id in remaining_spend:
                remaining_spend[match.rule.id] -= match.listing.current_price_ton
        return self._finish(
            WorkerReport(
                listings_seen=len(listings),
                matches_seen=len(matches),
                attempts_recorded=attempts_recorded,
            )
        )

    def _finish(self, report: WorkerReport) -> WorkerReport:
        self.last_report = report
        self.last_checked_at = now_iso()
        self.last_error = None
        return report

    async def run_forever(self, *, interval_seconds: float = 0.75, limit_per_market: int = 20) -> None:
        while True:
            started_at = perf_counter()
            try:
                report = await self.poll_once(limit_per_market=limit_per_market)
                logger.info("autobuy poll: %s", report)
            except Exception:
                self.last_error = "Marketplace connection is temporarily unavailable"
                logger.exception("autobuy poll failed")
            elapsed = perf_counter() - started_at
            await asyncio.sleep(max(0.0, interval_seconds - elapsed))
