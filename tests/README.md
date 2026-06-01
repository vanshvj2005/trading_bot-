# Tests

Run from the project root with the virtual env active:

```bash
pip install -r requirements.txt
pytest
```

## What is tested

- **`test_validators.py`** — full coverage of the pure validation functions:
  valid MARKET (BUY/SELL) and LIMIT orders normalise correctly; symbol and side
  normalisation (lowercase → uppercase, whitespace stripped); and the rejection
  paths — unknown side, zero/negative quantity, NaN/inf, non-numeric quantity,
  LIMIT missing price, MARKET *with* a price (this code rejects it),
  empty/junk symbols, and an **unsupported order type (STOP)** being rejected
  locally (see the Algo Order migration note in the main README). No mocks —
  these functions take no I/O.
- **`test_orders.py`** — the order functions with a **mocked** Binance client
  (no network). Verifies the exact `futures_create_order` call args for MARKET
  and LIMIT (including `timeInForce="GTC"` and `price`), that the response dict
  is returned unchanged, that a `BinanceAPIException` propagates **without**
  retrying (called once, exposes the exchange's code), and that a transient
  `requests.ConnectionError` retries **exactly once** before re-raising — and
  returns the response if the retry succeeds. `time.sleep` is patched so the
  backoff does not slow the suite.

## What is deliberately NOT tested, and why

- **End-to-end against the real Binance demo API.** Flaky, slow, and requires
  live credentials — unsuitable for a unit suite that must be green on a clean
  checkout. This path was instead **verified manually**: a live 0.001 BTC MARKET
  BUY returned `orderId=13674104195` and settled to `FILLED` on the dashboard
  (a matching SELL, `orderId=13674480112`, flattened the position).
- **The Binance library's internal HMAC request signing.** That is library
  code, not ours; testing it would be testing python-binance, not this project.
- **argparse parsing in `cli.py`.** The argument *values* flow straight into the
  validators, which are covered directly; testing argparse's own flag parsing is
  low value. The CLI's branching (exit codes per error type) is thin glue over
  the already-tested layers.
- **Interactive prompt flow (`-i`).** The prompting/confirmation loop is thin IO
  over the same validators (which are unit-tested) plus `input()`. It was
  exercised manually via piped stdin (valid entry, re-prompt on bad input, and a
  declined confirmation that places no order); a full `input()`-mocking test
  would mostly assert the mock, not behaviour.

## Design note — avoiding the tautology trap

The order tests mock only `futures_create_order` (the single method the code
calls) and then assert on **real behaviour**: the exact call arguments, the real
`BinanceAPIException` type and its `.code`, and the real retry *count*. They do
not assert "the mock returned what we told it to" — they assert what our code
*does* with the client, which is the part worth testing.
