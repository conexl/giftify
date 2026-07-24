# Giftify

Giftify is a staged Telegram gift auto-buying service.

Current phase:

- normalize MRKT and Portals listings into one domain model;
- collect gift characteristics and sale history;
- route market reads through a rotating proxy pool;
- expose the collector through backend service code.

The worker is safe by default: `PURCHASE_MODE=dry-run` only records matching lots. Direct MRKT purchase is available only when explicitly enabled.

## Run

```bash
uv run uvicorn giftify.main:app --reload --host 127.0.0.1 --port 8000
```

Open `http://127.0.0.1:8000/app`.

Run the low-latency worker in a separate terminal:

```bash
WORKER_POLL_INTERVAL_SECONDS=0.1 WORKER_LIMIT_PER_QUERY=20 uv run giftify-worker
```

For a deliberately rate-limited loop:

```bash
WORKER_POLL_INTERVAL_SECONDS=2 WORKER_LIMIT_PER_QUERY=10 uv run giftify-worker
```

By default the worker uses dry-run purchases. A generic external executor can be enabled with:

```bash
PURCHASE_MODE=real PURCHASE_ROUTE_URL=https://example.test/buy uv run uvicorn giftify.main:app
```

To use MRKT's direct purchase contract, set `PURCHASE_MODE=mrkt`. It sends the current lot identifier and price in nanotons to `/api/v1/gifts/buy`, checks the rule's maximum price immediately before the request, and attaches an idempotency key. Test this mode with a dedicated low-limit rule before relying on it in production.

Required token files default to `.secrets/mrkt_token.txt` and `.secrets/portals_token.txt`.

## Telegram notifications

To receive purchase and actionable error notifications, create a bot with [@BotFather](https://t.me/BotFather), send it `/start`, then add its token and your numeric chat ID to `.env`:

```dotenv
NOTIFICATION_BOT_TOKEN=123456:replace-with-bot-token
NOTIFICATION_CHAT_ID=123456789
NOTIFICATION_ERROR_COOLDOWN_SECONDS=300
```

The service sends confirmed purchase cards and alerts for insufficient balance, authorization failures, rate limits, and unconfirmed purchases. Error alerts of the same type are limited by the cooldown so they do not flood the chat.
