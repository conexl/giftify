from __future__ import annotations

import hashlib
import hmac
import json
from urllib.parse import parse_qsl


def parse_telegram_init_data(init_data: str, bot_token: str | None = None) -> dict[str, str] | None:
    if not init_data:
        return None
    try:
        parsed = dict(parse_qsl(init_data, keep_blank_values=True))
        if not parsed:
            return None
        hash_val = parsed.get("hash")
        if bot_token and hash_val:
            data_to_check = parsed.copy()
            data_to_check.pop("hash", None)
            data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(data_to_check.items()))
            secret_key = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
            calc_hash = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
            if not hmac.compare_digest(calc_hash, hash_val):
                return None
        return parsed
    except Exception:
        return None


def extract_user_id_from_init_data(init_data: str, bot_token: str | None = None) -> int | None:
    parsed = parse_telegram_init_data(init_data, bot_token)
    if not parsed or "user" not in parsed:
        return None
    try:
        user_info = json.loads(parsed["user"])
        user_id = user_info.get("id")
        return int(user_id) if user_id is not None else None
    except (json.JSONDecodeError, ValueError, TypeError):
        return None
