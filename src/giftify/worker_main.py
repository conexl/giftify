from __future__ import annotations

import asyncio
import logging

from .clients import MrktClient, PortalsClient
from .collector import GiftCollector
from .config import Settings
from .proxies import ProxyPool
from .purchases import purchase_executor_from_settings
from .notifications import TelegramNotifier
from .storage import SQLiteStore
from .tokens import StaticTokenProvider
from .worker import AutoBuyWorker


async def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    settings = Settings.from_env()
    proxy_pool = await ProxyPool.create(settings)
    store = SQLiteStore(settings.database_path)

    mrkt_token_provider = StaticTokenProvider(settings.mrkt_token_file)
    portals_token_provider = StaticTokenProvider(settings.portals_token_file)

    collector = GiftCollector(
        MrktClient(settings, proxy_pool, mrkt_token_provider),
        PortalsClient(settings, proxy_pool, portals_token_provider),
    )

    executor = purchase_executor_from_settings(
        settings,
        token_provider=mrkt_token_provider,
        portals_token_provider=portals_token_provider,
        proxy_pool=proxy_pool,
    )
    worker = AutoBuyWorker(collector, store, executor, notifier=TelegramNotifier.from_settings(settings))
    try:
        await worker.run_forever(
            interval_seconds=settings.worker_poll_interval_seconds,
            limit_per_market=settings.worker_limit_per_query,
        )
    finally:
        await collector.close()
        store.close()


def run() -> None:
    asyncio.run(main())


if __name__ == "__main__":
    run()
