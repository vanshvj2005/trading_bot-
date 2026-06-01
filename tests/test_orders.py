"""Tests for bot.orders — the Binance client is mocked; no network is hit.

These verify the two things that are genuinely ours: (1) that the order
functions translate their arguments into the correct ``futures_create_order``
call, and (2) that the retry/error policy behaves as specified — Binance API
errors propagate immediately (no retry), transient network errors retry exactly
once. ``time.sleep`` is patched so the retry backoff does not slow the suite.
"""

from __future__ import annotations

from typing import Any

import pytest
from requests.exceptions import ConnectionError as RequestsConnectionError

from bot.orders import place_limit_order, place_market_order

from .conftest import make_binance_api_exception

# --------------------------------------------------------------------------- #
# Correct request construction
# --------------------------------------------------------------------------- #


def test_place_market_order_calls_api_with_expected_params(fake_client: Any) -> None:
    """A market order maps to futures_create_order with type=MARKET, no price."""
    place_market_order(fake_client, symbol="BTCUSDT", side="BUY", quantity=0.001)
    fake_client.futures_create_order.assert_called_once_with(
        symbol="BTCUSDT", side="BUY", type="MARKET", quantity=0.001
    )


def test_place_limit_order_calls_api_with_expected_params(fake_client: Any) -> None:
    """A limit order includes price and timeInForce=GTC and type=LIMIT."""
    place_limit_order(
        fake_client, symbol="ETHUSDT", side="SELL", quantity=1.5, price=3000.0
    )
    fake_client.futures_create_order.assert_called_once_with(
        symbol="ETHUSDT",
        side="SELL",
        type="LIMIT",
        timeInForce="GTC",
        quantity=1.5,
        price=3000.0,
    )


def test_market_order_returns_the_api_response(fake_client: Any) -> None:
    """The raw exchange response dict is returned to the caller unchanged."""
    response = place_market_order(
        fake_client, symbol="BTCUSDT", side="BUY", quantity=0.001
    )
    assert response["orderId"] == 13674104195
    assert response["status"] == "NEW"


# --------------------------------------------------------------------------- #
# Error / retry policy
# --------------------------------------------------------------------------- #


def test_binance_api_error_propagates_without_retry(fake_client: Any) -> None:
    """A rejected order (BinanceAPIException) is re-raised and NOT retried."""
    fake_client.futures_create_order.side_effect = make_binance_api_exception(
        code=-1121, msg="Invalid symbol."
    )
    with pytest.raises(Exception) as exc_info:
        place_market_order(fake_client, symbol="NOPE", side="BUY", quantity=0.001)
    # Surfaces the exchange's own code/message, and was tried exactly once.
    assert exc_info.value.code == -1121
    assert fake_client.futures_create_order.call_count == 1


def test_network_error_retries_once_then_raises(
    fake_client: Any, mocker: Any
) -> None:
    """A persistent network error retries exactly once, then re-raises."""
    sleep = mocker.patch("bot.orders.time.sleep")
    fake_client.futures_create_order.side_effect = RequestsConnectionError("boom")
    with pytest.raises(RequestsConnectionError):
        place_market_order(fake_client, symbol="BTCUSDT", side="BUY", quantity=0.001)
    # Initial attempt + one retry == 2 calls; backoff slept exactly once.
    assert fake_client.futures_create_order.call_count == 2
    sleep.assert_called_once()


def test_network_error_then_success_returns_response(
    fake_client: Any, mocker: Any
) -> None:
    """If the retry succeeds, the order function returns that response."""
    mocker.patch("bot.orders.time.sleep")
    fake_client.futures_create_order.side_effect = [
        RequestsConnectionError("transient"),
        {"orderId": 999, "status": "NEW"},
    ]
    response = place_market_order(
        fake_client, symbol="BTCUSDT", side="BUY", quantity=0.001
    )
    assert response["orderId"] == 999
    assert fake_client.futures_create_order.call_count == 2
