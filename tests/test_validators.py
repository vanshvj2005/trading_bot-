"""Tests for bot.validators — pure functions, no mocks or network needed.

These cover both the happy paths (valid orders normalise correctly) and the
rejection paths (bad input raises InvalidOrderError). The rejection paths are
the highest-value tests here: rejecting bad input before any API call is the
whole point of this module.
"""

from __future__ import annotations

import pytest

from bot.validators import (
    InvalidOrderError,
    validate_order,
    validate_quantity,
    validate_side,
    validate_symbol,
)

# --------------------------------------------------------------------------- #
# Happy paths
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("side", ["BUY", "SELL"])
def test_valid_market_order_passes_for_both_sides(side: str) -> None:
    """A well-formed MARKET order normalises and has no price."""
    result = validate_order(
        symbol="BTCUSDT", side=side, order_type="MARKET", quantity="0.001"
    )
    assert result == {
        "symbol": "BTCUSDT",
        "side": side,
        "order_type": "MARKET",
        "quantity": 0.001,
        "price": None,
    }


def test_valid_limit_order_passes() -> None:
    """A well-formed LIMIT order keeps its price as a positive float."""
    result = validate_order(
        symbol="ETHUSDT",
        side="SELL",
        order_type="LIMIT",
        quantity="1.5",
        price="3000",
    )
    assert result == {
        "symbol": "ETHUSDT",
        "side": "SELL",
        "order_type": "LIMIT",
        "quantity": 1.5,
        "price": 3000.0,
    }


@pytest.mark.parametrize(
    "raw, expected",
    [("btcusdt", "BTCUSDT"), (" ethusdt ", "ETHUSDT"), ("BtcUsdt", "BTCUSDT")],
)
def test_symbol_is_normalised(raw: str, expected: str) -> None:
    """Symbols are upper-cased and stripped of surrounding whitespace."""
    assert validate_symbol(raw) == expected


@pytest.mark.parametrize("raw, expected", [("buy", "BUY"), ("sell", "SELL")])
def test_side_is_normalised(raw: str, expected: str) -> None:
    """Lowercase sides are accepted and normalised (so 'buy' is valid input)."""
    assert validate_side(raw) == expected


# --------------------------------------------------------------------------- #
# Rejection paths
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("bad_side", ["HOLD", "LONG", "", "  "])
def test_invalid_side_raises(bad_side: str) -> None:
    """An unrecognised side is rejected with a clear message."""
    with pytest.raises(InvalidOrderError, match="[Ss]ide"):
        validate_side(bad_side)


@pytest.mark.parametrize("bad_qty", ["-1", "0", "-0.5"])
def test_quantity_must_be_positive(bad_qty: str) -> None:
    """Zero or negative quantities are rejected."""
    with pytest.raises(InvalidOrderError, match="greater than 0"):
        validate_quantity(bad_qty)


@pytest.mark.parametrize("bad_qty", ["nan", "inf", "-inf"])
def test_quantity_rejects_non_finite(bad_qty: str) -> None:
    """NaN / infinity are rejected (a naive '> 0' check would let inf through)."""
    with pytest.raises(InvalidOrderError, match="finite"):
        validate_quantity(bad_qty)


@pytest.mark.parametrize("bad_qty", ["abc", "1.2.3", ""])
def test_quantity_rejects_non_numeric(bad_qty: str) -> None:
    """Non-numeric quantity strings are rejected as not a valid number."""
    with pytest.raises(InvalidOrderError, match="valid number"):
        validate_quantity(bad_qty)


def test_limit_order_without_price_raises() -> None:
    """A LIMIT order with no --price is rejected."""
    with pytest.raises(InvalidOrderError, match="Price is required"):
        validate_order(
            symbol="BTCUSDT", side="BUY", order_type="LIMIT", quantity="0.001"
        )


def test_market_order_with_price_is_rejected() -> None:
    """This code REJECTS a price on a MARKET order (rather than ignoring it)."""
    with pytest.raises(InvalidOrderError, match="must not be supplied"):
        validate_order(
            symbol="BTCUSDT",
            side="BUY",
            order_type="MARKET",
            quantity="0.001",
            price="95000",
        )


def test_unsupported_order_type_is_rejected() -> None:
    """STOP (and other conditional types) are rejected — see README migration note."""
    with pytest.raises(InvalidOrderError, match="invalid"):
        validate_order(
            symbol="BTCUSDT",
            side="SELL",
            order_type="STOP",
            quantity="0.001",
            price="90000",
        )


@pytest.mark.parametrize("bad_symbol", ["", "   ", "BTC-USDT", "BTC USDT"])
def test_invalid_symbol_raises(bad_symbol: str) -> None:
    """Empty or non-alphanumeric symbols are rejected."""
    with pytest.raises(InvalidOrderError):
        validate_symbol(bad_symbol)
