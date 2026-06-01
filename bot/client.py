"""Binance Futures Demo/Testnet client wrapper.

A thin wrapper around :class:`binance.client.Client` (python-binance) that
constructs the connection once and forces the Futures REST base URL to the
current Demo Futures endpoint.

URL note (read carefully): the task spec states the base URL is
``https://testnet.binancefuture.com``. Binance has since migrated this
environment to ``https://demo-fapi.binance.com`` (the renamed Futures Demo
endpoint, dashboard at https://demo.binance.com). With ``testnet=True``,
python-binance reads ``FUTURES_TESTNET_URL`` (not ``FUTURES_URL``) and its
bundled value still points at the stale host, so after construction we
explicitly override ``FUTURES_TESTNET_URL`` (and ``FUTURES_URL`` for
consistency) to the demo host. This module never targets production Binance.
"""

from __future__ import annotations

from binance.client import Client

from .logging_config import get_logger, redact_secret

#: The current Binance Futures Demo REST endpoint (NOT production).
DEMO_FUTURES_BASE_URL = "https://demo-fapi.binance.com"

#: python-binance builds futures request paths as
#: ``<configured-url>/<version>/<path>`` (e.g. ``.../fapi/v1/order``), so the
#: configured value must include the ``/fapi`` segment.
_FUTURES_URL = f"{DEMO_FUTURES_BASE_URL}/fapi"

logger = get_logger()


def build_client(api_key: str, api_secret: str) -> Client:
    """Construct a python-binance client pinned to the Demo Futures endpoint.

    The client is created with ``testnet=True`` and then has its Futures REST
    URL explicitly overridden to :data:`DEMO_FUTURES_BASE_URL`, because the
    library's bundled testnet URL may be stale.

    Args:
        api_key: Binance Demo/Testnet API key.
        api_secret: Binance Demo/Testnet API secret. Never logged.

    Returns:
        A configured :class:`binance.client.Client` whose Futures requests go
        to the demo endpoint.

    Raises:
        ValueError: If ``api_key`` or ``api_secret`` is empty.
    """
    if not api_key or not api_secret:
        raise ValueError(
            "API key and secret must both be provided. Copy .env.example to "
            ".env and fill in your Demo/Testnet credentials."
        )

    client = Client(api_key, api_secret, testnet=True)

    # Override the (stale) testnet Futures URL with the current demo host.
    #
    # IMPORTANT: with testnet=True, python-binance's _create_futures_api_uri
    # selects self.FUTURES_TESTNET_URL and IGNORES self.FUTURES_URL. The bundled
    # FUTURES_TESTNET_URL still points at the migrated-away host
    # (testnet.binancefuture.com), so we must override FUTURES_TESTNET_URL — that
    # is the attribute actually read for every futures_* request on this client.
    # We also set FUTURES_URL to the same host for safety/consistency.
    client.FUTURES_TESTNET_URL = _FUTURES_URL
    client.FUTURES_URL = _FUTURES_URL

    # Log connection setup with the secret redacted — never the raw value.
    logger.info(
        "Binance Futures Demo client constructed | base_url=%s | api_key=%s | "
        "api_secret=%s",
        DEMO_FUTURES_BASE_URL,
        redact_secret(api_key),
        redact_secret(api_secret),
    )
    return client
