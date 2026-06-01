"""Shared pytest fixtures and helpers for the trading-bot test suite.

Only what is genuinely reused lives here: a factory for building a real
:class:`binance.exceptions.BinanceAPIException` (its constructor needs a
response object and a JSON body), and a fake-client fixture for the order tests.
We use a real ``BinanceAPIException`` rather than a stand-in so the tests
exercise the actual exception type the code catches.
"""

from __future__ import annotations

import json
from typing import Any

import pytest
from binance.exceptions import BinanceAPIException


class _FakeResponse:
    """Minimal stand-in for a ``requests.Response`` used to build exceptions.

    ``BinanceAPIException.__init__`` reads ``response.text`` (on JSON-parse
    failure) and ``response.request``; this provides both.
    """

    def __init__(self, text: str, status_code: int = 400) -> None:
        self.text = text
        self.status_code = status_code
        self.request = None


def make_binance_api_exception(
    code: int = -1121, msg: str = "Invalid symbol."
) -> BinanceAPIException:
    """Build a real :class:`BinanceAPIException` with a given code and message.

    Args:
        code: Binance error code (e.g. ``-1121`` for invalid symbol).
        msg: Human-readable error message.

    Returns:
        A constructed ``BinanceAPIException`` whose ``.code`` and ``.message``
        match the arguments.
    """
    body = json.dumps({"code": code, "msg": msg})
    return BinanceAPIException(_FakeResponse(body), 400, body)


@pytest.fixture
def fake_client(mocker: Any) -> Any:
    """Return a mock python-binance client with a stubbed ``futures_create_order``.

    By default the stub returns a representative successful futures order
    response. Individual tests override ``return_value`` or ``side_effect`` as
    needed. The mock is intentionally shallow: the order functions only call
    ``futures_create_order``, so that is all we stub — no faking of the wider
    library surface.
    """
    client = mocker.Mock()
    client.futures_create_order.return_value = {
        "orderId": 13674104195,
        "symbol": "BTCUSDT",
        "status": "NEW",
        "executedQty": "0.000",
        "avgPrice": "0.00",
        "origQty": "0.001",
        "side": "BUY",
        "type": "MARKET",
    }
    return client
