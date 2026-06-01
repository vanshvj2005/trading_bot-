# Binance Futures Demo Trading Bot

A small, production-quality Python CLI that places **MARKET** and **LIMIT**
orders on the **Binance Futures Demo/Testnet (USDT-M)** environment. It can be
driven by flags (scriptable) or in an **interactive mode** that prompts
field-by-field and confirms before placing. It validates input before any API
call, places real orders against the demo endpoint, prints a clear
request/response summary, and logs every request, response, and error (with
timestamps and stack traces) to `logs/trading_bot.log`.

> ⚠️ **Safety:** This bot targets **DEMO/TESTNET only**. Never configure it
> with production Binance API keys. The base URL is hard-pinned to the demo
> host and the code never points at production Binance.

---

## ⚠️ Important: base URL changed since the task spec

The task specification states the base URL is:

```
https://testnet.binancefuture.com
```

Binance has since **migrated this environment** to its renamed Futures Demo
endpoint:

```
https://demo-fapi.binance.com
```

The dashboard for this environment now lives at **https://demo.binance.com**.

This bot uses the **current** endpoint, `https://demo-fapi.binance.com`. We do
this in two layers (see [`bot/client.py`](bot/client.py)):

1. Construct the python-binance client with `testnet=True`.
2. **Explicitly override** `client.FUTURES_TESTNET_URL` to
   `https://demo-fapi.binance.com/fapi`. This is the attribute that matters:
   in python-binance 1.0.19, when `testnet=True` the request-builder
   (`_create_futures_api_uri`) selects `FUTURES_TESTNET_URL` and **ignores**
   `FUTURES_URL`. The library's bundled `FUTURES_TESTNET_URL` still points at
   the migrated-away host (`testnet.binancefuture.com`), so overriding it is
   what actually redirects every futures request to the demo host. (We set
   `FUTURES_URL` to the same value too, for consistency.)

If you must run against the literal spec URL for some reason, change
`DEMO_FUTURES_BASE_URL` in [`bot/client.py`](bot/client.py) — but the demo host
is the correct, working target as of this writing.

---

## ⚠️ Note: conditional (STOP) orders and the Algo Order migration

This bot supports **MARKET and LIMIT only**, and that is a deliberate, informed
choice — not an oversight. A STOP (stop-limit) order type was built and then
**removed** after testing against the live demo endpoint, for a concrete reason:

- On **2025-12-09**, Binance migrated all USDⓈ-M Futures **conditional** order
  types — `STOP`, `STOP_MARKET`, `TAKE_PROFIT`, `TAKE_PROFIT_MARKET`,
  `TRAILING_STOP_MARKET` — off the standard `POST /fapi/v1/order` endpoint onto a
  new **Algo Order** endpoint, `POST /fapi/v1/algoOrder`.
- Placing a STOP via the standard order endpoint is now rejected with API error
  **`-4120`**: *"Order type not supported for this endpoint. Please use the Algo
  Order API endpoints instead."* (Confirmed live on the demo account.)
- The pinned **python-binance 1.0.19 has no Algo Order method** — it predates the
  change — so supporting conditional orders would mean either calling the new
  endpoint via the library's internal request method, or upgrading the library
  (which risks breaking the version-specific `FUTURES_TESTNET_URL` override
  above). Both were out of scope for this submission.

The validator therefore rejects STOP locally with a clear message (exit code 1)
rather than letting it round-trip to a `-4120` rejection. The supported types
live in `VALID_TYPES` in [`bot/validators.py`](bot/validators.py).

Reference: Binance USDⓈ-M Futures
[Change Log](https://developers.binance.com/docs/derivatives/change-log) and
[New Algo Order](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/rest-api/New-Algo-Order).

---

## What it does

- Accepts an order via CLI flags (`--symbol`, `--side`, `--type`,
  `--quantity`, and `--price` for LIMIT orders) — or via interactive prompts
  (`-i` / `--interactive`, or run with no order flags).
- Validates all input **before** any network call (rejects bad sides, negative
  or non-numeric quantities, missing/forbidden prices, etc.).
- Places a real order on the Futures Demo endpoint via
  [python-binance](https://github.com/sammchardy/python-binance).
- Prints (a) the request summary before sending, (b) the full order response
  (`orderId`, `status`, `executedQty`, `avgPrice` when available), and (c) a
  clear success/failure line.
- Logs everything to `logs/trading_bot.log`. **API secrets are never logged**,
  including in request headers.

---

## Project structure

```
trading_bot/
  bot/
    __init__.py
    client.py          # Binance Futures Demo client wrapper (URL override)
    orders.py          # order placement (market + limit), retry-on-network
    validators.py      # pure input validation, raises InvalidOrderError
    logging_config.py  # logging setup + secret redaction helper
  cli.py               # CLI entry point (argparse + interactive), no business logic
  tests/               # pytest suite (validators + orders, mocked client)
  logs/                # log files written here (gitignored)
  README.md
  requirements.txt
  .env.example         # template for API_KEY / API_SECRET
  .gitignore           # excludes .env and logs/
```

---

## Setup

```bash
# 1. From the trading_bot/ directory, create and activate a virtual env
python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate

# 2. Install pinned dependencies
pip install -r requirements.txt

# 3. Provide credentials
cp .env.example .env
# then edit .env and paste your Demo/Testnet API_KEY and API_SECRET
```

### How to get Demo/Testnet API keys

1. Go to **https://demo.binance.com**.
2. Open **API Management**.
3. Click **Create API** → choose **System Generated**.
4. Copy the **API Key** and **Secret Key** into your `.env` file.

These are demo credentials tied to a demo balance — they cannot touch real
funds.

---

## Usage

Run from the `trading_bot/` directory with your virtual env activated.

### Example 1 — MARKET order

Buy 0.001 BTC at the prevailing market price:

```bash
python cli.py --symbol BTCUSDT --side BUY --type MARKET --quantity 0.001
```

A market order executes immediately against the order book, so you do **not**
pass `--price` (doing so is rejected as invalid input).

### Example 2 — LIMIT order

Place a resting sell of 0.001 BTC at a price of 95,000 USDT (good-till-cancelled):

```bash
python cli.py --symbol BTCUSDT --side SELL --type LIMIT --quantity 0.001 --price 95000
```

A limit order requires `--price`; it rests on the book until filled or
cancelled. If the price is far from the market it may stay `NEW` (unfilled).

### Example 3 — Interactive mode

Run with `-i` (or with no order flags) to be prompted field-by-field, with
re-prompting on invalid input and a confirmation step before the order is sent:

```bash
python cli.py -i
```

### Exit codes

| Code | Meaning                                                        |
|------|----------------------------------------------------------------|
| `0`  | Success                                                        |
| `1`  | Invalid user input or missing configuration (validation, creds)|
| `2`  | Binance API error (order rejected) — shows error code + message|
| `3`  | Network failure after one retry                                |

---

## Logging

- All requests, responses, and errors are written to `logs/trading_bot.log`
  with timestamps.
- **INFO** for normal flow, **ERROR** (with stack traces) for failures.
- The API **secret is never logged** — not as a value and not via request
  headers. The connection log line masks credentials as `****(set, len=N)`
  (see `redact_secret` in [`bot/logging_config.py`](bot/logging_config.py)).
- The `logs/` directory is gitignored.

---

## Running tests

```bash
pip install -r requirements.txt
pytest
```

The suite covers input validation (pure functions) and order placement against
a **mocked** Binance client — it never hits the network. The end-to-end path was
verified manually against the live demo endpoint (see [tests/README.md](tests/README.md)
for what is and isn't tested, and why).

---

## Assumptions and limitations

- **Futures USDT-M only.** This bot uses the `futures_create_order` endpoint;
  it does not handle Spot, COIN-M, or other products.
- **Order types:** MARKET and LIMIT only. No conditional orders (STOP /
  STOP_MARKET / TAKE_PROFIT / TRAILING_STOP_MARKET) and no OCO/bracket/TWAP/grid.
  See the conditional-orders note below — this is a deliberate, informed choice.
- **LIMIT time-in-force** is fixed to `GTC` (good-till-cancelled).
- **Per-symbol exchange filters are not pre-validated locally.** Each symbol
  has a minimum quantity and notional, a price tick size, and a step size that
  only the exchange knows authoritatively (e.g. `BTCUSDT` has a **0.001 BTC
  minimum** quantity). The bot validates obviously-bad input locally
  (negative/zero/non-numeric, wrong side, missing price) but lets the exchange
  be the source of truth for filter violations — these surface honestly as a
  Binance API error (exit code 2) with the exchange's own code and message,
  rather than being faked client-side.
- **At-least-once retry semantics.** On a transient network failure the bot
  retries the order exactly once with a short backoff. If the original request
  reached the exchange but the *response* was lost, the retry could place a
  second order. Eliminating this requires an idempotency key
  (`newClientOrderId`), which is intentionally out of scope for this base
  submission. The retry behaviour matches the task spec's "retry once" rule.
- **No leverage/margin management.** The bot assumes the account's existing
  leverage and margin-type settings; it does not change them.

---

## Safety note

**This bot targets DEMO/TESTNET only; never configure it with production API
keys.** The base URL is pinned to `https://demo-fapi.binance.com` and the code
never points at production Binance. `.env` (your real credentials) is
gitignored and must never be committed.
