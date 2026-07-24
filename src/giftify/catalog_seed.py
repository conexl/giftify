from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any

from .domain import GiftListing, Market, number
from .storage import SQLiteStore

logger = logging.getLogger(__name__)
ID_LIKE_RE = re.compile(r"^(?:[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}|\d+)$", re.IGNORECASE)


def seed_catalog_from_snapshots(store: SQLiteStore, seed_dir: str | None) -> int:
    if not seed_dir or store.catalog_count() > 0:
        return 0

    root = Path(seed_dir)
    if not root.exists():
        return 0

    listings: list[GiftListing] = []
    for path in sorted(root.glob("listings-*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            logger.warning("Could not read catalog seed snapshot: %s", path)
            continue
        rows = payload.get("listings", []) if isinstance(payload, dict) else []
        for raw in rows:
            listing = _listing_from_snapshot(raw)
            if listing:
                listings.append(listing)

    if listings:
        store.upsert_catalog(listings)
    return len(listings)


def _listing_from_snapshot(raw: dict[str, Any]) -> GiftListing | None:
    market_value = raw.get("source") or raw.get("market")
    if market_value not in {Market.MRKT.value, Market.PORTALS.value}:
        return None
    listing_id = str(raw.get("listing_id") or raw.get("id") or "")
    collection = str(raw.get("collection") or "")
    model = str(raw.get("model") or "")
    backdrop = str(raw.get("backdrop") or "")
    if not listing_id or not collection or ID_LIKE_RE.match(collection):
        return None
    return GiftListing(
        market=Market(market_value),
        listing_id=listing_id,
        collection=collection,
        title=collection,
        current_price_ton=number(raw.get("current_price_ton")),
        model=model,
        symbol=str(raw.get("symbol") or "unknown"),
        backdrop=backdrop,
        market_link=str(raw.get("link") or ""),
        gift_number=number(raw.get("number")),
        model_rarity=number(raw.get("model_rarity")),
        symbol_rarity=number(raw.get("symbol_rarity")),
        backdrop_rarity=number(raw.get("backdrop_rarity")),
        raw=raw,
    )
