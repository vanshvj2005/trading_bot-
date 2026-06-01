#!/usr/bin/env python3
"""Command-line entry point for the Binance Futures Demo trading bot.

This layer is intentionally thin: it parses arguments (or prompts for them in
interactive mode), loads credentials, validates input, then delegates to
:mod:`bot.orders`. All business logic lives in the ``bot`` package. Human-facing
status is printed to the console; full detail (requests, responses, errors with
stack traces) goes to the log file.

Two ways to run:
    * Flags (scriptable):  --symbol/--side/--type/--quantity[/--price]
    * Interactive:         -i / --interactive, or run with no order flags. Prompts
      field-by-field (re-asking on bad input) and confirms before placing.

Exit codes:
    0  success (or interactive entry cancelled before placing — nothing went wrong)
    1  invalid user input / configuration (validation, missing credentials, cancel)
    2  Binance API error (order rejected, bad parameters) — see code + message
    3  network failure after one retry
"""

from __future__ import annotations

import argparse
import os
import sys
from typing import Any, Callable

from binance.exceptions import BinanceAPIException
from dotenv import load_dotenv
from requests.exceptions import RequestException

from bot.client import DEMO_FUTURES_BASE_URL, build_client
from bot.logging_config import get_logger
from bot.orders import place_limit_order, place_market_order
from bot.validators import (
    InvalidOrderError,
    validate_order,
    validate_order_type,
    validate_price,
    validate_quantity,
    validate_side,
    validate_symbol,
)

# Exit codes (documented in the module docstring).
EXIT_OK = 0
EXIT_INVALID_INPUT = 1
EXIT_API_ERROR = 2
EXIT_NETWORK_ERROR = 3

#: argparse flags that count as "the user supplied order parameters". If none
#: are present (and -i is not given), the CLI falls into interactive mode.
_ORDER_FLAGS = ("symbol", "side", "order_type", "quantity", "price")

logger = get_logger()


def build_parser() -> argparse.ArgumentParser:
    """Construct the argparse parser for the CLI.

    Order flags are not marked ``required`` at the argparse level because the
    interactive mode supplies them instead; missing values in flag mode are
    caught by the validators with clear messages.

    Returns:
        The configured :class:`argparse.ArgumentParser`.
    """
    parser = argparse.ArgumentParser(
        prog="trading-bot",
        description=(
            "Place a MARKET or LIMIT order on Binance Futures Demo/Testnet "
            f"(USDT-M). Targets {DEMO_FUTURES_BASE_URL} only — never production "
            "Binance. Run with -i for interactive mode."
        ),
        epilog=(
            "Examples:\n"
            "  python cli.py --symbol BTCUSDT --side BUY --type MARKET "
            "--quantity 0.001\n"
            "  python cli.py --symbol BTCUSDT --side SELL --type LIMIT "
            "--quantity 0.001 --price 95000\n"
            "  python cli.py -i        # interactive prompts\n"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "-i",
        "--interactive",
        action="store_true",
        help="Prompt for order fields interactively and confirm before placing.",
    )
    parser.add_argument("--symbol", help="Trading pair, e.g. BTCUSDT.")
    parser.add_argument(
        "--side", help="Order side: BUY or SELL (case-insensitive)."
    )
    parser.add_argument(
        "--type",
        dest="order_type",
        help="Order type: MARKET or LIMIT (case-insensitive).",
    )
    parser.add_argument(
        "--quantity", help="Order quantity (positive number), e.g. 0.001."
    )
    parser.add_argument(
        "--price",
        default=None,
        help="Limit price (required for LIMIT orders, forbidden for MARKET).",
    )
    return parser


def load_credentials() -> tuple[str, str]:
    """Load API credentials from the environment (.env supported).

    Returns:
        A ``(api_key, api_secret)`` tuple.

    Raises:
        InvalidOrderError: If either credential is missing. Treated as a
            configuration/input error (exit code 1).
    """
    load_dotenv()
    api_key = os.getenv("API_KEY", "").strip()
    api_secret = os.getenv("API_SECRET", "").strip()
    if not api_key or not api_secret:
        raise InvalidOrderError(
            "Missing API credentials. Copy .env.example to .env and set "
            "API_KEY and API_SECRET with your Binance Demo/Testnet keys."
        )
    return api_key, api_secret


def _prompt_field(label: str, validator: Callable[[str], Any]) -> Any:
    """Prompt for a single field, re-asking until the validator accepts it.

    Args:
        label: The prompt label shown to the user.
        validator: A function that normalises/validates the raw string and
            raises :class:`InvalidOrderError` on bad input.

    Returns:
        The validated, normalised value.

    Raises:
        EOFError / KeyboardInterrupt: Propagated so the caller can treat them
            as a cancellation (not swallowed).
    """
    while True:
        raw = input(f"  {label}: ").strip()
        try:
            return validator(raw)
        except InvalidOrderError as exc:
            # Re-prompt with the validator's own clear message.
            print(f"    ✗ {exc}", file=sys.stderr)


def collect_order_interactively() -> dict[str, Any]:
    """Collect and validate order parameters via interactive prompts.

    Only prompts for the fields the chosen order type needs (e.g. no price for
    MARKET), so the returned dict matches :func:`validate_order`'s shape without
    needing a second cross-field check.

    Returns:
        A normalised order-parameter dict.

    Raises:
        EOFError / KeyboardInterrupt: If the user cancels (handled by caller).
    """
    print("Interactive order entry — Binance Futures DEMO/TESTNET")
    print(f"Endpoint: {DEMO_FUTURES_BASE_URL}")
    print("(Press Ctrl-C to cancel at any time.)\n")

    symbol = _prompt_field("Symbol (e.g. BTCUSDT)", validate_symbol)
    side = _prompt_field("Side [BUY/SELL]", validate_side)
    order_type = _prompt_field("Type [MARKET/LIMIT]", validate_order_type)
    quantity = _prompt_field("Quantity (e.g. 0.001)", validate_quantity)

    price = None
    if order_type == "LIMIT":
        price = _prompt_field(
            "Limit price", lambda r: validate_price(r, order_type)
        )

    return {
        "symbol": symbol,
        "side": side,
        "order_type": order_type,
        "quantity": quantity,
        "price": price,
    }


def _confirm() -> bool:
    """Ask the user to confirm placement. Returns True only on an explicit yes.

    Raises:
        EOFError / KeyboardInterrupt: Propagated as cancellation.
    """
    answer = input("Place this order on the DEMO endpoint? [y/N]: ").strip().lower()
    return answer in ("y", "yes")


def _print_request_summary(params: dict[str, Any]) -> None:
    """Print the order request summary to the console before sending.

    Args:
        params: Normalised order parameters from :func:`validate_order`.
    """
    print("=" * 60)
    print("ORDER REQUEST")
    print(f"  Endpoint   : {DEMO_FUTURES_BASE_URL} (DEMO/TESTNET)")
    print(f"  Symbol     : {params['symbol']}")
    print(f"  Side       : {params['side']}")
    print(f"  Type       : {params['order_type']}")
    print(f"  Quantity   : {params['quantity']}")
    if params["order_type"] == "LIMIT":
        print(f"  Price      : {params['price']}")
    print("=" * 60)


def _print_order_response(response: dict[str, Any]) -> None:
    """Print the salient fields of a Binance order response to the console.

    Args:
        response: The raw Binance order response dict.
    """
    print("ORDER RESPONSE")
    print(f"  orderId     : {response.get('orderId')}")
    print(f"  status      : {response.get('status')}")
    print(f"  executedQty : {response.get('executedQty')}")
    # avgPrice is present on futures responses; show it when meaningful.
    avg_price = response.get("avgPrice")
    if avg_price is not None:
        print(f"  avgPrice    : {avg_price}")
    print("=" * 60)


def _place_order(client: Any, params: dict[str, Any]) -> dict[str, Any]:
    """Dispatch to the right order function based on the order type.

    Args:
        client: A configured python-binance client.
        params: Normalised order parameters.

    Returns:
        The raw Binance order response dict.
    """
    if params["order_type"] == "MARKET":
        return place_market_order(
            client,
            symbol=params["symbol"],
            side=params["side"],
            quantity=params["quantity"],
        )
    # order_type == "LIMIT"
    return place_limit_order(
        client,
        symbol=params["symbol"],
        side=params["side"],
        quantity=params["quantity"],
        price=params["price"],
    )


def run(argv: list[str] | None = None) -> int:
    """Parse arguments, validate, place the order, and report the outcome.

    Args:
        argv: Argument list (defaults to ``sys.argv[1:]`` when ``None``).

    Returns:
        A process exit code (see module docstring).
    """
    parser = build_parser()
    args = parser.parse_args(argv)

    # Interactive if explicitly requested, or if no order flags were supplied.
    interactive = args.interactive or not any(
        getattr(args, flag) is not None for flag in _ORDER_FLAGS
    )

    # 1) Load credentials and gather/validate parameters BEFORE any network work.
    try:
        api_key, api_secret = load_credentials()
        if interactive:
            params = collect_order_interactively()
        else:
            params = validate_order(
                symbol=args.symbol,
                side=args.side,
                order_type=args.order_type,
                quantity=args.quantity,
                price=args.price,
            )
    except InvalidOrderError as exc:
        logger.error("Invalid input or configuration: %s", exc)
        print(f"ERROR (invalid input): {exc}", file=sys.stderr)
        return EXIT_INVALID_INPUT
    except (EOFError, KeyboardInterrupt):
        logger.info("Order entry cancelled by user (interrupt/EOF).")
        print("\nCancelled — no order placed.", file=sys.stderr)
        return EXIT_INVALID_INPUT

    _print_request_summary(params)

    # Interactive mode confirms before placing a real (demo) order.
    if interactive:
        try:
            if not _confirm():
                logger.info("Order not placed — user declined confirmation.")
                print("No order placed (cancelled by user).")
                return EXIT_OK
        except (EOFError, KeyboardInterrupt):
            logger.info("Confirmation cancelled by user (interrupt/EOF).")
            print("\nCancelled — no order placed.", file=sys.stderr)
            return EXIT_INVALID_INPUT

    # 2) Build the client and place the order.
    try:
        client = build_client(api_key, api_secret)
        response = _place_order(client, params)
    except BinanceAPIException as exc:
        # Deterministic exchange rejection: surface code + message.
        logger.error(
            "Binance API error placing order: code=%s message=%s",
            exc.code,
            exc.message,
            exc_info=True,
        )
        print(
            f"FAILURE: Binance API error [code {exc.code}]: {exc.message}",
            file=sys.stderr,
        )
        return EXIT_API_ERROR
    except RequestException as exc:
        # Network failure that survived the single retry in orders.py.
        logger.error("Network failure placing order: %s", exc, exc_info=True)
        print(
            f"FAILURE: network error contacting {DEMO_FUTURES_BASE_URL} "
            f"after one retry: {exc}",
            file=sys.stderr,
        )
        return EXIT_NETWORK_ERROR

    # 3) Report success.
    _print_order_response(response)
    print(
        f"SUCCESS: {params['order_type']} {params['side']} order placed "
        f"(orderId={response.get('orderId')}, status={response.get('status')})."
    )
    logger.info(
        "Order placed successfully | orderId=%s status=%s",
        response.get("orderId"),
        response.get("status"),
    )
    return EXIT_OK


def main() -> None:
    """Console entry point: run the CLI and exit with its status code."""
    sys.exit(run())


if __name__ == "__main__":
    main()
