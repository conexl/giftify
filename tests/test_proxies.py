import asyncio
import unittest

from giftify.proxies import ProxyPool, parse_configured_proxies, parse_http_proxies


class ProxyParsingTest(unittest.TestCase):
    def test_parse_http_proxies_keeps_unique_http_urls(self):
        text = """
        1.1.1.1:8080
        http://2.2.2.2:3128
        http://2.2.2.2:3128
        socks5://3.3.3.3:1080
        bad-line
        http://missing-port
        """

        proxies = parse_http_proxies(text, limit=10)

        self.assertEqual(set(proxies), {"http://1.1.1.1:8080", "http://2.2.2.2:3128"})

    def test_accepts_configured_socks_proxies(self):
        proxies = parse_configured_proxies(
            ("socks5://user:pass@127.0.0.1:1080", "invalid", "https://proxy.example:443")
        )

        self.assertEqual(proxies, ["socks5://user:pass@127.0.0.1:1080", "https://proxy.example:443"])


class ProxyPoolTest(unittest.IsolatedAsyncioTestCase):
    async def test_failed_proxies_are_skipped_until_marked_successful(self):
        pool = ProxyPool(["http://1.1.1.1:8080", "http://2.2.2.2:3128"])

        first = await pool.next()
        await pool.mark_failed(first)

        self.assertEqual(await pool.next(), "http://2.2.2.2:3128")
        self.assertEqual(pool.stats().failed, 1)

        await pool.mark_success(first)
        active = {await pool.next(), await pool.next()}

        self.assertEqual(active, {"http://1.1.1.1:8080", "http://2.2.2.2:3128"})
        self.assertEqual(pool.stats().failed, 0)


if __name__ == "__main__":
    unittest.main()
