import unittest

from giftify.domain import GiftListing, Market
from giftify.rules import AutoBuyRule, RuleMatcher


def listing(**overrides):
    base = dict(
        market=Market.MRKT,
        listing_id="gift-1",
        collection="Cool Gift",
        title="Cool Gift #1",
        current_price_ton=10.0,
        model="Dragon",
        symbol="Star",
        backdrop="Blue",
        market_link="https://example.test",
    )
    base.update(overrides)
    return GiftListing(**base)


class RuleMatcherTest(unittest.TestCase):
    def test_collection_rule_matches_any_model_under_max_price(self):
        rule = AutoBuyRule(id=1, user_id=10, collection="Cool Gift", max_price_ton=11)

        matches = RuleMatcher().match([rule], [listing(model="Other")])

        self.assertEqual(len(matches), 1)

    def test_model_and_backdrop_rule_requires_both(self):
        rule = AutoBuyRule(
            id=1,
            user_id=10,
            collection="Cool Gift",
            model="Dragon",
            backdrop="Blue",
            max_price_ton=11,
        )

        matches = RuleMatcher().match([rule], [listing(backdrop="Red"), listing(backdrop="Blue")])

        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0].listing.backdrop, "Blue")

    def test_price_must_be_less_or_equal_to_max(self):
        rule = AutoBuyRule(id=1, user_id=10, collection="Cool Gift", max_price_ton=9.99)

        self.assertEqual(RuleMatcher().match([rule], [listing()]), [])

    def test_rule_does_not_match_when_it_would_exceed_spend_limit(self):
        rule = AutoBuyRule(
            id=1,
            user_id=10,
            collection="Cool Gift",
            max_price_ton=11,
            max_spend_ton=15,
            spent_ton=8,
        )

        self.assertEqual(RuleMatcher().match([rule], [listing(current_price_ton=8)]), [])


if __name__ == "__main__":
    unittest.main()
