"""Trading bot package for Binance Futures Demo/Testnet (USDT-M).

This package wraps the Binance Futures Demo REST API behind a small,
testable surface: a connection wrapper (:mod:`bot.client`), pure order
placement functions (:mod:`bot.orders`), input validation
(:mod:`bot.validators`), and logging setup (:mod:`bot.logging_config`).

WARNING: This package targets the DEMO/TESTNET environment only. Never
configure it with production Binance API keys.
"""

__all__ = ["client", "orders", "validators", "logging_config"]
