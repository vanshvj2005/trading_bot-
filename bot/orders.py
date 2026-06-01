"""Order placement against Binance Futures Demo.

Pure-ish functions that take an already-constructed python-binance client and
place real orders on the demo testnet. There are NO CLI concerns here and NO
mocking — every call hits the live demo endpoint.

Network resilience: transient network failures (connection errors, timeouts)
are retried exactly once with a short exponential backoff before being
re-raised, per the task spec. Binance API errors (rejected orders, bad
parameters) are NOT retried — they are deterministic and re-raising lets the
caller surface the exchange's error code and message.
"""

from __future__ import annotations

import time
from typing import Any, Callable

from binance.client import Client
from binance.exceptions import BinanceAPIException
from requests.exceptions import ConnectionError as RequestsConnectionError
from requests.exceptions import Timeout as RequestsTimeout

from .logging_config import get_logger

logger = get_logger()

#: Network exceptions worth retrying once (transient by nature).
_RETRYABLE_NETWORK_ERRORS = (RequestsConnectionError, RequestsTimeout)
#: Backoff (seconds) before the single retry of a transient network failure.
_RETRY_BACKOFF_SECONDS = 1.0


def _call_with_retry(
    operation: Callable[[], dict[str, Any]],
    description: str,
) -> dict[str, Any]:
    """Run a network operation, retrying once on transient network failures.

    Binance API exceptions are re-raised immediately (not retried), since a
    rejected order will be rejected identically on retry.

    Args:
        operation: Zero-arg callable performing the API request.
        description: Human-readable label for logging, e.g. ``"MARKET BUY"``.

    Returns:
        The raw Binance order response dict.

    Raises:
        BinanceAPIException: If the exchange rejects the request.
        requests.exceptions.RequestException: If the network fails on both the
            initial attempt and the single retry.
    """
    try:
        return operation()
    except _RETRYABLE_NETWORK_ERRORS as exc:
        logger.error(
            "Network failure on %s (attempt 1/2): %s. Retrying in %.1fs.",
            description,
            exc,
            _RETRY_BACKOFF_SECONDS,
            exc_info=True,
        )
        time.sleep(_RETRY_BACKOFF_SECONDS)
        try:
            return operation()
        except _RETRYABLE_NETWORK_ERRORS as retry_exc:
            logger.error(
                "Network failure on %s (attempt 2/2): %s. Giving up.",
                description,
                retry_exc,
                exc_info=True,
            )
            raise


def place_market_order(
    client: Client,
    symbol: str,
    side: str,
    quantity: float,
) -> dict[str, Any]:
    """Place a MARKET order on Binance Futures Demo.

    Args:
        client: A configured python-binance client (see :mod:`bot.client`).
        symbol: Normalised trading symbol, e.g. ``"BTCUSDT"``.
        side: ``"BUY"`` or ``"SELL"``.
        quantity: Order quantity (positive).

    Returns:
        The raw Binance order response dict (includes ``orderId``, ``status``,
        ``executedQty``, ``avgPrice``, etc.).

    Raises:
        BinanceAPIException: If the exchange rejects the order.
        requests.exceptions.RequestException: On unrecoverable network failure.
    """
    description = f"MARKET {side} {quantity} {symbol}"
    logger.info("Submitting order | %s", description)

    def _operation() -> dict[str, Any]:
        return client.futures_create_order(
            symbol=symbol,
            side=side,
            type="MARKET",
            quantity=quantity,
        )

    response = _call_with_retry(_operation, description)
    logger.info("Order response | %s | %s", description, response)
    return response


def place_limit_order(
    client: Client,
    symbol: str,
    side: str,
    quantity: float,
    price: float,
) -> dict[str, Any]:
    """Place a LIMIT order on Binance Futures Demo.

    Uses time-in-force ``GTC`` (good-till-cancelled), the standard default for
    a resting limit order.

    Args:
        client: A configured python-binance client (see :mod:`bot.client`).
        symbol: Normalised trading symbol, e.g. ``"BTCUSDT"``.
        side: ``"BUY"`` or ``"SELL"``.
        quantity: Order quantity (positive).
        price: Limit price (positive).

    Returns:
        The raw Binance order response dict (includes ``orderId``, ``status``,
        ``executedQty``, ``avgPrice``, etc.).

    Raises:
        BinanceAPIException: If the exchange rejects the order.
        requests.exceptions.RequestException: On unrecoverable network failure.
    """
    description = f"LIMIT {side} {quantity} {symbol} @ {price}"
    logger.info("Submitting order | %s", description)

    def _operation() -> dict[str, Any]:
        return client.futures_create_order(
            symbol=symbol,
            side=side,
            type="LIMIT",
            timeInForce="GTC",
            quantity=quantity,
            price=price,
        )

    response = _call_with_retry(_operation, description)
    logger.info("Order response | %s | %s", description, response)
    return response
