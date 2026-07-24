import os
import unittest
from unittest.mock import patch

from giftify.config import Settings


class SettingsTest(unittest.TestCase):
    def test_worker_poll_interval_is_low_latency_by_default(self):
        with patch.dict(os.environ, {}, clear=True), patch("giftify.config._dotenv_values", return_value={}):
            settings = Settings.from_env()

        self.assertEqual(settings.worker_poll_interval_seconds, 0.1)
        self.assertEqual(settings.worker_limit_per_query, 50)

    def test_worker_poll_interval_can_be_reduced(self):
        with patch.dict(os.environ, {"WORKER_POLL_INTERVAL_SECONDS": "0.5", "WORKER_LIMIT_PER_QUERY": "10"}), patch(
            "giftify.config._dotenv_values", return_value={}
        ):
            settings = Settings.from_env()

        self.assertEqual(settings.worker_poll_interval_seconds, 0.5)
        self.assertEqual(settings.worker_limit_per_query, 10)

    def test_reads_tma_refresh_settings_from_dotenv(self):
        env_file = {
            "TMA_REFRESH_ENABLED": "true",
            "TG_APP_ID": "12345",
            "TG_APP_HASH": "hash",
            "PYROGRAM_SESSION": ".secrets/pyrogram.session",
            "TG_PROXY_HOST": "127.0.0.1",
            "TG_PROXY_PORT": "1080",
            "TG_PROXY_SCHEME": "socks5",
        }

        with patch.dict(os.environ, {}, clear=True), patch("giftify.config._dotenv_values", return_value=env_file):
            settings = Settings.from_env()

        self.assertTrue(settings.tma_refresh_enabled)
        self.assertEqual(settings.tg_app_id, 12345)
        self.assertEqual(settings.tg_app_hash, "hash")
        self.assertEqual(settings.tma_session_path, ".secrets/pyrogram.session")
        self.assertEqual(settings.telegram_proxy, {"scheme": "socks5", "hostname": "127.0.0.1", "port": 1080})

    def test_reads_explicit_market_proxy_urls(self):
        with patch.dict(os.environ, {"MARKET_PROXY_URLS": "socks5://user:pass@127.0.0.1:1080"}, clear=True), patch(
            "giftify.config._dotenv_values", return_value={}
        ):
            settings = Settings.from_env()

        self.assertEqual(settings.market_proxy_urls, ("socks5://user:pass@127.0.0.1:1080",))

    def test_reads_notification_settings(self):
        with patch.dict(
            os.environ,
            {"NOTIFICATION_BOT_TOKEN": "token", "NOTIFICATION_CHAT_ID": "-100123"},
            clear=True,
        ), patch("giftify.config._dotenv_values", return_value={}):
            settings = Settings.from_env()

        self.assertEqual(settings.notification_bot_token, "token")
        self.assertEqual(settings.notification_chat_id, "-100123")


if __name__ == "__main__":
    unittest.main()
