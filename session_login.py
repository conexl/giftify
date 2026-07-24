"""Interactive, one-time login for replacing the Telegram Pyrogram session."""

from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, timezone
from pathlib import Path

from .config import Settings


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Sign in to Telegram and save a Pyrogram session")
    parser.add_argument(
        "--replace",
        action="store_true",
        help="back up the existing session and sign in to a different Telegram account",
    )
    return parser


def login(*, replace: bool) -> Path:
    settings = Settings.from_env()
    if not settings.tg_app_id or not settings.tg_app_hash:
        raise RuntimeError("TG_APP_ID and TG_APP_HASH must be configured")

    session_path = Path(settings.tma_session_path).expanduser().resolve()
    session_path.parent.mkdir(parents=True, exist_ok=True)
    if replace and session_path.exists():
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        backup_path = session_path.with_suffix(f".backup-{stamp}.session")
        session_path.replace(backup_path)
        print(f"Previous session backed up to {backup_path}")

    # Pyrogram's sync facade expects an event loop even before Client.start().
    asyncio.set_event_loop(asyncio.new_event_loop())
    from pyrogram import Client

    with Client(
        name=session_path.stem,
        api_id=settings.tg_app_id,
        api_hash=settings.tg_app_hash,
        proxy=settings.telegram_proxy,
        workdir=str(session_path.parent),
        no_updates=True,
    ) as app:
        user = app.get_me()
        print(f"Telegram session updated for account id {user.id}.")
    return session_path


def main() -> None:
    args = _parser().parse_args()
    login(replace=args.replace)


if __name__ == "__main__":
    main()
