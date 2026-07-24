from __future__ import annotations

import asyncio
import html
import logging
from dataclasses import dataclass
from time import monotonic

import httpx

from .config import Settings
from .domain import GiftListing
from .purchases import PurchaseResult, PurchaseStatus

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Notification:
    text: str
    dedupe_key: str | None = None


class TelegramNotifier:
    """Best-effort outbound notifications that never block the purchase path."""

    def __init__(
        self,
        bot_token: str | None,
        chat_id: str | None,
        *,
        error_cooldown_seconds: int = 300,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._bot_token = bot_token
        self._chat_id = chat_id
        self._error_cooldown_seconds = error_cooldown_seconds
        self._transport = transport
        self._last_error_at: dict[str, float] = {}

    @classmethod
    def from_settings(cls, settings: Settings) -> "TelegramNotifier":
        return cls(
            settings.notification_bot_token,
            settings.notification_chat_id,
            error_cooldown_seconds=settings.notification_error_cooldown_seconds,
        )

    @property
    def configured(self) -> bool:
        return bool(self._bot_token and self._chat_id)

    def publish_attempt(self, listing: GiftListing, result: PurchaseResult) -> None:
        notification = self._notification_for(listing, result)
        if notification is None:
            return
        if notification.dedupe_key and not self._accept_error(notification.dedupe_key):
            return
        task = asyncio.create_task(self.send(notification.text))
        task.add_done_callback(_log_task_failure)

    async def send(self, text: str) -> bool:
        if not self.configured:
            return False
        assert self._bot_token is not None and self._chat_id is not None
        url = f"https://api.telegram.org/bot{self._bot_token}/sendMessage"
        payload = {"chat_id": self._chat_id, "text": text, "parse_mode": "HTML", "disable_web_page_preview": True}
        for attempt in range(2):
            try:
                async with httpx.AsyncClient(timeout=8.0, transport=self._transport) as client:
                    response = await client.post(url, json=payload)
            except httpx.TransportError:
                if attempt == 0:
                    await asyncio.sleep(0.25)
                    continue
                logger.warning("Telegram notification transport failed")
                return False
            if response.is_success and response.json().get("ok") is True:
                return True
            if response.status_code == 429 and attempt == 0:
                retry_after = response.json().get("parameters", {}).get("retry_after", 1)
                await asyncio.sleep(min(float(retry_after), 5.0))
                continue
            if response.status_code >= 500 and attempt == 0:
                await asyncio.sleep(0.25)
                continue
            logger.warning("Telegram notification was rejected with HTTP %s", response.status_code)
            return False
        return False

    def _notification_for(self, listing: GiftListing, result: PurchaseResult) -> Notification | None:
        if result.status == PurchaseStatus.SUCCESS:
            return Notification(_purchase_message(listing))
        if result.status not in {
            PurchaseStatus.INSUFFICIENT_BALANCE,
            PurchaseStatus.AUTH_FAILED,
            PurchaseStatus.RATE_LIMITED,
            PurchaseStatus.FAILED,
        }:
            return None
        return Notification(_error_message(listing, result), dedupe_key=result.status.value)

    def _accept_error(self, key: str) -> bool:
        now = monotonic()
        previous = self._last_error_at.get(key)
        if previous is not None and now - previous < self._error_cooldown_seconds:
            return False
        self._last_error_at[key] = now
        return True


def _purchase_message(listing: GiftListing) -> str:
    title = _escape(listing.title or listing.collection or "Подарок")
    gift_url = _safe_url(listing.tg_link) or _safe_url(listing.market_link)
    title_line = f'<a href="{gift_url}">{title}</a>' if gift_url else title
    lines = ["🎉 <b>GIFT PURCHASED!</b>", "", f"🏷 {title_line}"]
    for label, value in (("Model", listing.model), ("Backdrop", listing.backdrop)):
        if value:
            lines.append(f"├ {label}: {_escape(value)}")
    lines.append(f"├ Price: {listing.current_price_ton:.3f} TON")
    market_url = _safe_url(listing.market_link)
    market = listing.market.value.upper()
    lines.append(f'└ Bought on <a href="{market_url}">{market}</a>' if market_url else f"└ Bought on {market}")
    floors = [("Floor gift", listing.floor_gift_ton), ("Floor model", listing.floor_model_ton)]
    known_floors = [(label, value) for label, value in floors if value is not None]
    if known_floors:
        lines.append("")
        lines.extend(f"💳 {label}: {value:.3f} TON" for label, value in known_floors)
    return "\n".join(lines)


def _error_message(listing: GiftListing, result: PurchaseResult) -> str:
    labels = {
        PurchaseStatus.INSUFFICIENT_BALANCE: "недостаточно баланса",
        PurchaseStatus.AUTH_FAILED: "не удалось авторизоваться",
        PurchaseStatus.RATE_LIMITED: "MRKT ограничил частоту запросов",
        PurchaseStatus.FAILED: "покупка не подтверждена",
    }
    title = _escape(listing.title or listing.collection or "Подарок")
    lines = [f"⚠️ <b>Giftify: {labels[result.status]}</b>", "", f"🏷 {title}", f"├ Price: {listing.current_price_ton:.3f} TON"]
    if listing.market_link:
        lines.append(f'└ <a href="{_safe_url(listing.market_link)}">Открыть лот в {listing.market.value.upper()}</a>')
    return "\n".join(lines)


def _safe_url(value: str | None) -> str:
    text = str(value or "")
    return html.escape(text, quote=True) if text.startswith("https://") else ""


def _escape(value: object) -> str:
    return html.escape(str(value), quote=False)


def _log_task_failure(task: asyncio.Task[object]) -> None:
    try:
        task.result()
    except asyncio.CancelledError:
        return
    except Exception:
        logger.exception("Telegram notification task failed")
