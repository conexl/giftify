from __future__ import annotations

import sqlite3
import threading
from dataclasses import dataclass
from pathlib import Path

from .domain import GiftListing, Market, display_value
from .purchases import PurchaseResult
from .rules import AutoBuyRule, NewRule, now_iso


@dataclass(frozen=True)
class PurchaseAttempt:
    id: int
    rule_id: int
    user_id: int
    market: Market
    listing_id: str
    price_ton: float
    status: str
    message: str
    idempotency_key: str
    created_at: str


@dataclass(frozen=True)
class CatalogOption:
    market: Market
    collection: str
    model: str | None
    backdrop: str | None
    symbol: str | None
    min_price_ton: float
    last_seen_at: str


@dataclass(frozen=True)
class ListingRecord:
    market: Market
    listing_id: str
    collection: str
    title: str
    current_price_ton: float
    model: str
    symbol: str
    backdrop: str
    market_link: str
    tg_link: str | None
    gift_number: float
    model_rarity: float
    symbol_rarity: float
    backdrop_rarity: float
    floor_gift_ton: float | None
    floor_model_ton: float | None
    photo_url: str | None
    first_seen_at: str
    last_seen_at: str


@dataclass(frozen=True)
class SavedGift:
    id: int
    rule_id: int
    rule_collection: str
    market: Market
    listing_id: str
    title: str
    collection: str
    model: str
    backdrop: str
    symbol: str
    gift_number: float
    model_rarity: float
    symbol_rarity: float
    backdrop_rarity: float
    price_ton: float
    floor_gift_ton: float | None
    photo_url: str | None
    market_link: str | None
    tg_link: str | None
    saved_at: str


class SQLiteStore:
    def __init__(self, path: str = "state/giftify.sqlite3") -> None:
        self._path = Path(path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(self._path, timeout=30.0, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        with self._lock:
            self._conn.execute("PRAGMA journal_mode=WAL;")
            self._conn.execute("PRAGMA synchronous=NORMAL;")
            self._conn.execute("PRAGMA busy_timeout=30000;")
            self.migrate()

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    def migrate(self) -> None:
        with self._lock:
            self._conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS rules (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    market TEXT,
                    collection TEXT NOT NULL,
                    model TEXT,
                    backdrop TEXT,
                    max_price_ton REAL NOT NULL,
                    enabled INTEGER NOT NULL DEFAULT 1,
                    max_quantity INTEGER,
                    max_spend_ton REAL,
                    purchased_count INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS purchase_attempts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    rule_id INTEGER NOT NULL,
                    user_id INTEGER NOT NULL,
                    market TEXT NOT NULL,
                    listing_id TEXT NOT NULL,
                    price_ton REAL NOT NULL,
                    status TEXT NOT NULL,
                    message TEXT NOT NULL,
                    idempotency_key TEXT NOT NULL UNIQUE,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS catalog_options (
                    market TEXT NOT NULL,
                    collection TEXT NOT NULL,
                    model TEXT,
                    backdrop TEXT,
                    symbol TEXT,
                    min_price_ton REAL NOT NULL,
                    last_seen_at TEXT NOT NULL,
                    PRIMARY KEY (market, collection, model, backdrop, symbol)
                );

                CREATE TABLE IF NOT EXISTS gift_listing_history (
                    market TEXT NOT NULL,
                    listing_id TEXT NOT NULL,
                    collection TEXT NOT NULL,
                    title TEXT NOT NULL,
                    current_price_ton REAL NOT NULL,
                    model TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    backdrop TEXT NOT NULL,
                    market_link TEXT NOT NULL,
                    tg_link TEXT,
                    gift_number REAL NOT NULL,
                    model_rarity REAL NOT NULL,
                    symbol_rarity REAL NOT NULL,
                    backdrop_rarity REAL NOT NULL,
                    floor_gift_ton REAL,
                    floor_model_ton REAL,
                    photo_url TEXT,
                    first_seen_at TEXT NOT NULL,
                    last_seen_at TEXT NOT NULL,
                    PRIMARY KEY (market, listing_id)
                );

                CREATE TABLE IF NOT EXISTS bot_settings (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    is_paused INTEGER NOT NULL DEFAULT 1,
                    updated_at TEXT NOT NULL
                );
                """
            )
            rule_columns = {row["name"] for row in self._conn.execute("PRAGMA table_info(rules)").fetchall()}
            if "max_spend_ton" not in rule_columns:
                self._conn.execute("ALTER TABLE rules ADD COLUMN max_spend_ton REAL")
            attempt_columns = {row["name"] for row in self._conn.execute("PRAGMA table_info(purchase_attempts)").fetchall()}
            if "is_archived" not in attempt_columns:
                self._conn.execute("ALTER TABLE purchase_attempts ADD COLUMN is_archived INTEGER NOT NULL DEFAULT 0")
            self._conn.execute(
                "INSERT OR IGNORE INTO bot_settings (id, is_paused, updated_at) VALUES (1, 1, ?)",
                (now_iso(),),
            )
            self._conn.commit()

    def create_rule(self, rule: NewRule) -> AutoBuyRule:
        rule.validate()
        timestamp = now_iso()
        with self._lock:
            cursor = self._conn.execute(
                """
                INSERT INTO rules (
                    user_id, market, collection, model, backdrop, max_price_ton,
                    enabled, max_spend_ton, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    rule.user_id,
                    rule.market.value if rule.market else None,
                    rule.collection,
                    rule.model,
                    rule.backdrop,
                    rule.max_price_ton,
                    int(rule.enabled),
                    rule.max_spend_ton,
                    timestamp,
                    timestamp,
                ),
            )
            self._conn.commit()
            last_id = int(cursor.lastrowid)
        return self.get_rule(last_id)

    def get_rule(self, rule_id: int) -> AutoBuyRule:
        with self._lock:
            rows = self._rule_rows("WHERE rules.id = ?", [rule_id])
            row = rows[0] if rows else None
            if row is None:
                raise KeyError(f"rule not found: {rule_id}")
            return _rule_from_row(row)

    def list_rules(self, *, enabled_only: bool = False, user_id: int | None = None) -> list[AutoBuyRule]:
        clauses: list[str] = []
        args: list[object] = []
        if enabled_only:
            clauses.append("rules.enabled = 1")
        if user_id is not None:
            clauses.append("rules.user_id = ?")
            args.append(user_id)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        with self._lock:
            rows = self._rule_rows(where, args)
            return [_rule_from_row(row) for row in rows]

    def _rule_rows(self, where: str = "", args: list[object] | None = None) -> list[sqlite3.Row]:
        return self._conn.execute(
            f"""
            SELECT
                rules.*,
                COALESCE(SUM(CASE WHEN purchase_attempts.status IN ('dry_run', 'success') THEN purchase_attempts.price_ton ELSE 0 END), 0) AS spent_ton
            FROM rules
            LEFT JOIN purchase_attempts ON purchase_attempts.rule_id = rules.id
            {where}
            GROUP BY rules.id
            ORDER BY rules.id
            """,
            args or [],
        ).fetchall()

    def delete_rule(self, rule_id: int, *, user_id: int | None = None) -> bool:
        clauses = ["id = ?"]
        args: list[object] = [rule_id]
        if user_id is not None:
            clauses.append("user_id = ?")
            args.append(user_id)
        with self._lock:
            cursor = self._conn.execute(f"DELETE FROM rules WHERE {' AND '.join(clauses)}", args)
            self._conn.commit()
            return cursor.rowcount > 0

    def set_rule_enabled(self, rule_id: int, enabled: bool, *, user_id: int | None = None) -> bool:
        clauses = ["id = ?"]
        args: list[object] = [int(enabled), now_iso(), rule_id]
        if user_id is not None:
            clauses.append("user_id = ?")
            args.append(user_id)
        with self._lock:
            cursor = self._conn.execute(
                f"UPDATE rules SET enabled = ?, updated_at = ? WHERE {' AND '.join(clauses)}",
                args,
            )
            self._conn.commit()
            return cursor.rowcount > 0

    def is_bot_paused(self) -> bool:
        with self._lock:
            row = self._conn.execute("SELECT is_paused FROM bot_settings WHERE id = 1").fetchone()
            return bool(row["is_paused"]) if row is not None else False

    def set_bot_paused(self, is_paused: bool) -> None:
        with self._lock:
            self._conn.execute(
                "UPDATE bot_settings SET is_paused = ?, updated_at = ? WHERE id = 1",
                (int(is_paused), now_iso()),
            )
            self._conn.commit()

    def record_attempt(self, rule: AutoBuyRule, listing: GiftListing, result: PurchaseResult, idempotency_key: str) -> bool:
        with self._lock:
            try:
                self._conn.execute(
                    """
                    INSERT INTO purchase_attempts (
                        rule_id, user_id, market, listing_id, price_ton,
                        status, message, idempotency_key, created_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        rule.id,
                        rule.user_id,
                        listing.market.value,
                        listing.listing_id,
                        listing.current_price_ton,
                        result.status.value,
                        result.message,
                        idempotency_key,
                        now_iso(),
                    ),
                )
            except sqlite3.IntegrityError:
                return False
            self._conn.commit()
            return True

    def has_final_attempt(self, idempotency_key: str) -> bool:
        """Whether this listing has already received a terminal real purchase outcome."""
        with self._lock:
            row = self._conn.execute(
                """
                SELECT 1
                FROM purchase_attempts
                WHERE idempotency_key = ?
                  AND status IN ('success', 'price_changed', 'already_sold', 'insufficient_balance', 'auth_failed', 'failed')
                LIMIT 1
                """,
                (idempotency_key,),
            ).fetchone()
            return row is not None

    def list_attempts(self) -> list[PurchaseAttempt]:
        with self._lock:
            rows = self._conn.execute("SELECT * FROM purchase_attempts ORDER BY id").fetchall()
            return [_attempt_from_row(row) for row in rows]

    def list_purchases(self) -> list[PurchaseAttempt]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM purchase_attempts WHERE status IN ('success', 'dry_run') ORDER BY id DESC"
            ).fetchall()
            return [_attempt_from_row(row) for row in rows]

    def list_saved_gifts(
        self, *, limit: int = 200, statuses: tuple[str, ...] = ("dry_run", "success")
    ) -> list[SavedGift]:
        if not statuses:
            return []
        status_placeholders = ", ".join("?" for _ in statuses)
        with self._lock:
            rows = self._conn.execute(
                f"""
                SELECT
                    purchase_attempts.id,
                    purchase_attempts.rule_id,
                    rules.collection AS rule_collection,
                    purchase_attempts.market,
                    purchase_attempts.listing_id,
                    purchase_attempts.price_ton,
                    purchase_attempts.created_at AS saved_at,
                    gift_listing_history.title,
                    gift_listing_history.collection,
                    gift_listing_history.model,
                    gift_listing_history.backdrop,
                    gift_listing_history.symbol,
                    gift_listing_history.gift_number,
                    gift_listing_history.model_rarity,
                    gift_listing_history.symbol_rarity,
                    gift_listing_history.backdrop_rarity,
                    gift_listing_history.floor_gift_ton,
                    gift_listing_history.photo_url,
                    gift_listing_history.market_link,
                    gift_listing_history.tg_link
                FROM purchase_attempts
                LEFT JOIN rules ON rules.id = purchase_attempts.rule_id
                LEFT JOIN gift_listing_history
                    ON gift_listing_history.market = purchase_attempts.market
                    AND gift_listing_history.listing_id = purchase_attempts.listing_id
                WHERE purchase_attempts.status IN ({status_placeholders})
                    AND COALESCE(purchase_attempts.is_archived, 0) = 0
                GROUP BY purchase_attempts.market, purchase_attempts.listing_id
                ORDER BY purchase_attempts.id DESC
                LIMIT ?
                """,
                (*statuses, limit),
            ).fetchall()
            return [_saved_gift_from_row(row) for row in rows]

    def list_purchased_gifts(self, *, limit: int = 200) -> list[SavedGift]:
        """Return only purchases confirmed by a marketplace, never dry-run matches."""
        return self.list_saved_gifts(limit=limit, statuses=("success",))

    def archive_saved_gift(self, gift_id: int) -> bool:
        with self._lock:
            cursor = self._conn.execute(
                "UPDATE purchase_attempts SET is_archived = 1 WHERE id = ?",
                (gift_id,),
            )
            self._conn.commit()
            return cursor.rowcount > 0

    def archive_all_saved_gifts(self) -> int:
        with self._lock:
            cursor = self._conn.execute(
                "UPDATE purchase_attempts SET is_archived = 1 WHERE status IN ('success', 'dry_run') AND COALESCE(is_archived, 0) = 0",
            )
            self._conn.commit()
            return cursor.rowcount

    def get_collection_photos(self) -> dict[str, str]:
        """Map collection -> photo_url from gift_listing_history."""
        with self._lock:
            rows = self._conn.execute(
                """
                SELECT collection, photo_url
                FROM gift_listing_history
                WHERE photo_url IS NOT NULL AND photo_url != ''
                GROUP BY collection
                """
            ).fetchall()
            return {row["collection"]: row["photo_url"] for row in rows}

    def get_model_photos(self, collection: str | None = None) -> dict[str, str]:
        """Map model -> photo_url from gift_listing_history."""
        where = "WHERE photo_url IS NOT NULL AND photo_url != '' AND model IS NOT NULL AND model != ''"
        args: list[object] = []
        if collection:
            where += " AND collection = ?"
            args.append(collection)
        with self._lock:
            rows = self._conn.execute(
                f"""
                SELECT model, photo_url
                FROM gift_listing_history
                {where}
                GROUP BY model
                """,
                args,
            ).fetchall()
            return {row["model"]: row["photo_url"] for row in rows}

    def upsert_catalog(self, listings: list[GiftListing]) -> None:
        timestamp = now_iso()
        with self._lock:
            for listing in listings:
                self._conn.execute(
                    """
                    INSERT INTO catalog_options (
                        market, collection, model, backdrop, symbol, min_price_ton, last_seen_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(market, collection, model, backdrop, symbol)
                    DO UPDATE SET
                        min_price_ton = MIN(catalog_options.min_price_ton, excluded.min_price_ton),
                        last_seen_at = excluded.last_seen_at
                    """,
                    (
                        listing.market.value,
                        listing.collection or listing.title,
                        listing.model or None,
                        listing.backdrop or None,
                        listing.symbol or None,
                        listing.current_price_ton,
                        timestamp,
                    ),
                )
            self._conn.commit()

    def upsert_listing_history(self, listings: list[GiftListing]) -> None:
        timestamp = now_iso()
        with self._lock:
            for listing in listings:
                self._conn.execute(
                    """
                    INSERT INTO gift_listing_history (
                        market, listing_id, collection, title, current_price_ton,
                        model, symbol, backdrop, market_link, tg_link, gift_number,
                        model_rarity, symbol_rarity, backdrop_rarity,
                        floor_gift_ton, floor_model_ton, photo_url,
                        first_seen_at, last_seen_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(market, listing_id)
                    DO UPDATE SET
                        collection = excluded.collection,
                        title = excluded.title,
                        current_price_ton = excluded.current_price_ton,
                        model = excluded.model,
                        symbol = excluded.symbol,
                        backdrop = excluded.backdrop,
                        market_link = excluded.market_link,
                        tg_link = excluded.tg_link,
                        gift_number = excluded.gift_number,
                        model_rarity = excluded.model_rarity,
                        symbol_rarity = excluded.symbol_rarity,
                        backdrop_rarity = excluded.backdrop_rarity,
                        floor_gift_ton = excluded.floor_gift_ton,
                        floor_model_ton = excluded.floor_model_ton,
                        photo_url = excluded.photo_url,
                        last_seen_at = excluded.last_seen_at
                    """,
                    (
                        listing.market.value,
                        listing.listing_id,
                        listing.collection or listing.title,
                        listing.title or listing.collection,
                        listing.current_price_ton,
                        listing.model,
                        listing.symbol,
                        listing.backdrop,
                        listing.market_link,
                        listing.tg_link,
                        listing.gift_number,
                        listing.model_rarity,
                        listing.symbol_rarity,
                        listing.backdrop_rarity,
                        listing.floor_gift_ton,
                        listing.floor_model_ton,
                        listing.photo_url,
                        timestamp,
                        timestamp,
                    ),
                )
            self._conn.commit()

    def list_listing_history(
        self,
        *,
        market: Market | None = None,
        collection: str | None = None,
        model: str | None = None,
        backdrop: str | None = None,
        max_price_ton: float | None = None,
        query: str | None = None,
        limit: int = 500,
    ) -> list[ListingRecord]:
        clauses: list[str] = []
        args: list[object] = []
        if market:
            clauses.append("market = ?")
            args.append(market.value)
        if collection:
            clauses.append("collection = ?")
            args.append(collection)
        if model:
            clauses.append("model = ?")
            args.append(model)
        if backdrop:
            clauses.append("backdrop = ?")
            args.append(backdrop)
        if max_price_ton is not None:
            clauses.append("current_price_ton <= ?")
            args.append(max_price_ton)
        if query:
            like = f"%{query.casefold()}%"
            clauses.append(
                """(
                    lower(title) LIKE ?
                    OR lower(collection) LIKE ?
                    OR lower(model) LIKE ?
                    OR lower(symbol) LIKE ?
                    OR lower(backdrop) LIKE ?
                    OR lower(listing_id) LIKE ?
                    OR CAST(gift_number AS TEXT) LIKE ?
                    OR lower(market) LIKE ?
                )"""
            )
            args.extend([like] * 8)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        with self._lock:
            rows = self._conn.execute(
                f"""
                SELECT * FROM gift_listing_history
                {where}
                ORDER BY last_seen_at DESC
                LIMIT ?
                """,
                [*args, limit],
            ).fetchall()
            return [_listing_record_from_row(row) for row in rows]

    def list_catalog(self) -> list[CatalogOption]:
        with self._lock:
            rows = self._conn.execute(
                """
                SELECT * FROM catalog_options
                ORDER BY collection COLLATE NOCASE, model COLLATE NOCASE, backdrop COLLATE NOCASE
                """
            ).fetchall()
            return [_catalog_from_row(row) for row in rows]

    def catalog_count(self) -> int:
        with self._lock:
            row = self._conn.execute("SELECT COUNT(*) AS total FROM catalog_options").fetchone()
            return int(row["total"])


def _rule_from_row(row: sqlite3.Row) -> AutoBuyRule:
    return AutoBuyRule(
        id=int(row["id"]),
        user_id=int(row["user_id"]),
        market=Market(row["market"]) if row["market"] else None,
        collection=str(row["collection"]),
        model=row["model"],
        backdrop=row["backdrop"],
        max_price_ton=float(row["max_price_ton"]),
        enabled=bool(row["enabled"]),
        max_spend_ton=float(row["max_spend_ton"]) if row["max_spend_ton"] is not None else None,
        spent_ton=float(row["spent_ton"]) if "spent_ton" in row.keys() else 0,
        created_at=str(row["created_at"]),
        updated_at=str(row["updated_at"]),
    )


def _attempt_from_row(row: sqlite3.Row) -> PurchaseAttempt:
    return PurchaseAttempt(
        id=int(row["id"]),
        rule_id=int(row["rule_id"]),
        user_id=int(row["user_id"]),
        market=Market(row["market"]),
        listing_id=str(row["listing_id"]),
        price_ton=float(row["price_ton"]),
        status=str(row["status"]),
        message=str(row["message"]),
        idempotency_key=str(row["idempotency_key"]),
        created_at=str(row["created_at"]),
    )


def _catalog_from_row(row: sqlite3.Row) -> CatalogOption:
    return CatalogOption(
        market=Market(row["market"]),
        collection=str(row["collection"]),
        model=row["model"],
        backdrop=row["backdrop"],
        symbol=row["symbol"],
        min_price_ton=float(row["min_price_ton"]),
        last_seen_at=str(row["last_seen_at"]),
    )


def _listing_record_from_row(row: sqlite3.Row) -> ListingRecord:
    return ListingRecord(
        market=Market(row["market"]),
        listing_id=str(row["listing_id"]),
        collection=str(row["collection"]),
        title=str(row["title"]),
        current_price_ton=float(row["current_price_ton"]),
        model=str(row["model"]),
        symbol=str(row["symbol"]),
        backdrop=str(row["backdrop"]),
        market_link=str(row["market_link"]),
        tg_link=row["tg_link"],
        gift_number=float(row["gift_number"]),
        model_rarity=float(row["model_rarity"]),
        symbol_rarity=float(row["symbol_rarity"]),
        backdrop_rarity=float(row["backdrop_rarity"]),
        floor_gift_ton=float(row["floor_gift_ton"]) if row["floor_gift_ton"] is not None else None,
        floor_model_ton=float(row["floor_model_ton"]) if row["floor_model_ton"] is not None else None,
        photo_url=row["photo_url"],
        first_seen_at=str(row["first_seen_at"]),
        last_seen_at=str(row["last_seen_at"]),
    )


def _saved_gift_from_row(row: sqlite3.Row) -> SavedGift:
    collection = display_value(row["collection"]) or display_value(row["rule_collection"], fallback="Подарок")
    title = display_value(row["title"]) or collection
    return SavedGift(
        id=int(row["id"]),
        rule_id=int(row["rule_id"]),
        rule_collection=display_value(row["rule_collection"], fallback=collection),
        market=Market(row["market"]),
        listing_id=str(row["listing_id"]),
        title=title,
        collection=collection,
        model=str(row["model"] or ""),
        backdrop=str(row["backdrop"] or ""),
        symbol=str(row["symbol"] or ""),
        gift_number=float(row["gift_number"] or 0),
        model_rarity=float(row["model_rarity"] or 0),
        symbol_rarity=float(row["symbol_rarity"] or 0),
        backdrop_rarity=float(row["backdrop_rarity"] or 0),
        price_ton=float(row["price_ton"]),
        floor_gift_ton=float(row["floor_gift_ton"]) if row["floor_gift_ton"] is not None else None,
        photo_url=row["photo_url"],
        market_link=row["market_link"],
        tg_link=row["tg_link"],
        saved_at=str(row["saved_at"]),
    )
