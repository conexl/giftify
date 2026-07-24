import unittest

import httpx

from giftify.domain import GiftListing, Market
from giftify.notifications import TelegramNotifier
from giftify.purchases import PurchaseResult, PurchaseStatus


def listing() -> GiftListing:
    return GiftListing(
        market=Market.MRKT,
        listing_id="gift-1",
        collection="Swag Bag",
        title="Swag Bag #109734",
        current_price_ton=1883.0,
        model="Gin and Juice",
        symbol="Star",
        backdrop="Persimmon",
        market_link="https://t.me/mrkt/app?startapp=gift-1",
        tg_link="https://t.me/nft/SwagBag-109734",
        floor_gift_ton=1800.0,
    )


class TelegramNotifierTest(unittest.IsolatedAsyncioTestCase):
    async def test_sends_html_purchase_template(self):
        captured: dict[str, object] = {}

        async def handler(request: httpx.Request) -> httpx.Response:
            captured["url"] = str(request.url)
            captured["payload"] = request.content.decode()
            return httpx.Response(200, json={"ok": True, "result": {"message_id": 1}})

        notifier = TelegramNotifier(
            "test-token", "-100123", transport=httpx.MockTransport(handler)
        )
        notification = notifier._notification_for(listing(), PurchaseResult(PurchaseStatus.SUCCESS, "bought"))

        self.assertIsNotNone(notification)
        sent = await notifier.send(notification.text)

        self.assertTrue(sent)
        self.assertIn("sendMessage", captured["url"])
        self.assertIn("GIFT PURCHASED", captured["payload"])
        self.assertIn("Gin and Juice", captured["payload"])

    def test_deduplicates_error_notifications_by_status(self):
        notifier = TelegramNotifier("test-token", "1", error_cooldown_seconds=300)
        error = PurchaseResult(PurchaseStatus.INSUFFICIENT_BALANCE, "insufficient")

        first = notifier._notification_for(listing(), error)
        second = notifier._notification_for(listing(), error)

        self.assertIsNotNone(first)
        self.assertIsNotNone(second)
        self.assertTrue(notifier._accept_error(first.dedupe_key or ""))
        self.assertFalse(notifier._accept_error(second.dedupe_key or ""))
