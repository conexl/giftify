from pathlib import Path
import unittest


class StaticAppTest(unittest.TestCase):
    def test_mini_app_assets_exist(self):
        root = Path("src/giftify/static")
        self.assertTrue((root / "app.html").exists())
        self.assertTrue((root / "app.js").exists())
        self.assertTrue((root / "styles.css").exists())

    def test_mini_app_manages_rules_and_shows_saved_matches_without_purchase_actions(self):
        html = Path("src/giftify/static/app.html").read_text(encoding="utf-8")
        script = Path("src/giftify/static/app.js").read_text(encoding="utf-8")
        self.assertIn('class="ruleComposer"', html)
        self.assertIn('id="collectionInput"', html)
        self.assertNotIn('list="collectionOptions"', html)
        self.assertNotIn('id="collectionOptions"', html)
        self.assertIn('id="modelInput"', html)
        self.assertIn('id="modelMenu"', html)
        self.assertIn('data-picker="model"', html)
        self.assertIn('id="backdropInput"', html)
        self.assertIn('id="backdropMenu"', html)
        self.assertIn('data-picker="backdrop"', html)
        self.assertIn('id="botToggleButton"', html)
        self.assertIn('id="savedGiftsList"', html)
        self.assertIn('id="giftSearchInput"', html)
        self.assertIn('id="giftMarketFilter"', html)
        self.assertIn('id="giftDetailsModal"', html)
        self.assertIn('id="rulesList"', html)
        self.assertIn('id="confirmModal"', html)
        self.assertIn("/api/v1/bot-status", script)
        self.assertIn("/api/v1/bot-status/pause", script)
        self.assertIn('requestJson("/api/v1/rules"', script)
        self.assertIn('method: "DELETE"', script)
        self.assertIn('requestJson("/api/v1/catalog"', script)
        self.assertIn('requestJson("/api/v1/saved-gifts"', script)
        self.assertIn("const AUTO_REFRESH_MS = 3000", script)
        self.assertIn("displayText", script)
        self.assertIn("createOptionPicker", script)
        self.assertIn("ArrowDown", script)
        self.assertIn("ArrowUp", script)
        self.assertNotIn('fillDatalist("modelOptions"', script)
        self.assertNotIn('fillDatalist("backdropOptions"', script)
        self.assertIn("openRuleModal", script)
        self.assertNotIn("/api/v1/worker/poll", script)


if __name__ == "__main__":
    unittest.main()
