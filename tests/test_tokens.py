import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from giftify.tokens import TmaTokenProvider, extract_init_data


class TokenHelpersTest(unittest.TestCase):
    def test_extract_init_data_from_query_or_fragment(self):
        self.assertEqual(extract_init_data("https://example.test/?tgWebAppData=user%3D1"), "user=1")
        self.assertEqual(extract_init_data("https://example.test/#tgWebAppData=user%3D2"), "user=2")


class TmaTokenProviderTest(unittest.IsolatedAsyncioTestCase):
    async def test_refreshes_from_telegram_when_static_tokens_are_disabled(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            token_path = Path(tmpdir) / "mrkt_token.txt"
            token_path.write_text("old-account-token", encoding="utf-8")
            provider = TmaTokenProvider(
                SimpleNamespace(static_tokens_enabled=False, tma_refresh_enabled=True),
                "mrkt",
                str(token_path),
                ttl_seconds=3600,
            )
            provider._refresh_sync = lambda: "telegram-session-token"  # type: ignore[method-assign]

            token = await provider.get_token()

            self.assertEqual(token, "telegram-session-token")
            self.assertEqual(token_path.read_text(encoding="utf-8"), "telegram-session-token")


if __name__ == "__main__":
    unittest.main()
