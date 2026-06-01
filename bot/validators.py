"""Pure input validation for trading-bot orders.

These functions validate user-supplied order parameters and raise
:class:`InvalidOrderError` with a clear, actionable message on bad input.
This module performs NO network or API calls — it is deliberately easy to
unit-test in isolation.

Validation is intentionally conservative: it rejects obviously-invalid input
(negative quantities, unknown sides, missing limit price) but does not attempt
to enforce per-symbol exchange filters (tick size, min notional), which only
the exchange knows authoritatively. Those are surfaced as Binance API errors at
order time.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation

#: Order sides accepted by Binance Futures.
VALID_SIDES = ("BUY", "SELL")
#: Order types this bot supports.
#:
#: NOTE: conditional types (STOP / STOP_MARKET / TAKE_PROFIT / ...) are
#: intentionally NOT supported. Binance migrated them off /fapi/v1/order onto a
#: separate Algo Order endpoint on 2025-12-09; placing one via the standard
#: order endpoint is rejected with code -4120. See the README for the full note.
VALID_TYPES = ("MARKET", "LIMIT")


class InvalidOrderError(ValueError):
    """Raised when user-supplied order parameters fail validation.

    Subclasses :class:`ValueError` so callers may catch either. The message is
    intended to be shown directly to the user on the CLI.
    """


def validate_symbol(symbol: str) -> str:
    """Validate and normalise a trading symbol.

    Args:
        symbol: Raw symbol string, e.g. ``"btcusdt"``.

    Returns:
        The symbol upper-cased and stripped, e.g. ``"BTCUSDT"``.

    Raises:
        InvalidOrderError: If the symbol is empty or not alphanumeric.
    """
    if symbol is None or not symbol.strip():
        raise InvalidOrderError("Symbol is required (e.g. BTCUSDT).")
    normalised = symbol.strip().upper()
    if not normalised.isalnum():
        raise InvalidOrderError(
            f"Symbol {symbol!r} is invalid: expected an alphanumeric pair "
            "like BTCUSDT."
        )
    return normalised


def validate_side(side: str) -> str:
    """Validate and normalise an order side.

    Args:
        side: Raw side string, case-insensitive.

    Returns:
        ``"BUY"`` or ``"SELL"``.

    Raises:
        InvalidOrderError: If the side is not one of :data:`VALID_SIDES`.
    """
    if side is None or not side.strip():
        raise InvalidOrderError("Side is required: choose BUY or SELL.")
    normalised = side.strip().upper()
    if normalised not in VALID_SIDES:
        raise InvalidOrderError(
            f"Side {side!r} is invalid: expected one of {', '.join(VALID_SIDES)}."
        )
    return normalised


def validate_order_type(order_type: str) -> str:
    """Validate and normalise an order type.

    Args:
        order_type: Raw type string, case-insensitive.

    Returns:
        ``"MARKET"`` or ``"LIMIT"``.

    Raises:
        InvalidOrderError: If the type is not one of :data:`VALID_TYPES`.
    """
    if order_type is None or not order_type.strip():
        raise InvalidOrderError("Order type is required: choose MARKET or LIMIT.")
    normalised = order_type.strip().upper()
    if normalised not in VALID_TYPES:
        raise InvalidOrderError(
            f"Order type {order_type!r} is invalid: expected one of "
            f"{', '.join(VALID_TYPES)}."
        )
    return normalised


def _to_positive_float(raw: float | str, label: str) -> float:
    """Parse ``raw`` to a strictly-positive, finite ``float`` or raise.

    Shared by quantity and price validation so the numeric rules (valid number,
    finite, > 0) live in one place.

    Args:
        raw: The value to parse.
        label: Human-readable field name for error messages, e.g. ``"Price"``.

    Returns:
        ``raw`` as a positive ``float``.

    Raises:
        InvalidOrderError: If ``raw`` is non-numeric, non-finite, or <= 0.
    """
    try:
        value = Decimal(str(raw))
    except (InvalidOperation, TypeError, ValueError):
        raise InvalidOrderError(f"{label} {raw!r} is not a valid number.") from None
    if not value.is_finite():
        raise InvalidOrderError(f"{label} {raw!r} must be a finite number.")
    if value <= 0:
        raise InvalidOrderError(f"{label} must be greater than 0 (got {raw!r}).")
    return float(value)


def validate_quantity(quantity: float | str | None) -> float:
    """Validate an order quantity.

    Args:
        quantity: Raw quantity as a number or numeric string.

    Returns:
        The quantity as a positive ``float``.

    Raises:
        InvalidOrderError: If the quantity is missing, not a number, or is not
            strictly positive.
    """
    if quantity is None:
        raise InvalidOrderError("Quantity is required (e.g. 0.001).")
    return _to_positive_float(quantity, "Quantity")


def validate_price(price: float | str | None, order_type: str) -> float | None:
    """Validate a limit price relative to the order type.

    Args:
        price: Raw price as a number/numeric string, or ``None`` if omitted.
        order_type: Already-validated order type (``"MARKET"`` or ``"LIMIT"``).

    Returns:
        The price as a positive ``float`` for ``LIMIT`` orders, or ``None`` for
        ``MARKET`` orders.

    Raises:
        InvalidOrderError: If a ``LIMIT`` order has no/invalid/non-positive
            price, or if a price is supplied for a ``MARKET`` order.
    """
    if order_type == "MARKET":
        if price is not None:
            raise InvalidOrderError(
                "Price must not be supplied for a MARKET order; market orders "
                "execute at the prevailing market price."
            )
        return None

    # order_type == "LIMIT"
    if price is None:
        raise InvalidOrderError("Price is required for a LIMIT order (use --price).")
    return _to_positive_float(price, "Price")


def validate_order(
    symbol: str,
    side: str,
    order_type: str,
    quantity: float | str,
    price: float | str | None = None,
) -> dict[str, object]:
    """Validate a complete order and return normalised parameters.

    Runs every field validator and cross-checks price against order type.

    Args:
        symbol: Raw trading symbol.
        side: Raw order side.
        order_type: Raw order type.
        quantity: Raw quantity.
        price: Raw limit price, or ``None``.

    Returns:
        A dict with normalised keys ``symbol``, ``side``, ``order_type``,
        ``quantity``, and ``price`` (``price`` is ``None`` for MARKET orders).

    Raises:
        InvalidOrderError: If any field fails validation.
    """
    norm_symbol = validate_symbol(symbol)
    norm_side = validate_side(side)
    norm_type = validate_order_type(order_type)
    norm_qty = validate_quantity(quantity)
    norm_price = validate_price(price, norm_type)
    return {
        "symbol": norm_symbol,
        "side": norm_side,
        "order_type": norm_type,
        "quantity": norm_qty,
        "price": norm_price,
    }
