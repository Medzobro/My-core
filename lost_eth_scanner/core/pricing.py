"""Minimal price feed: ETH -> USD, with two public fallbacks and a TTL cache.

Prices are cosmetic (they turn raw amounts into a human comparison). When no
feed is reachable the audit still works and simply omits the USD column.
"""

from __future__ import annotations

import time
from typing import Optional

import aiohttp

SOURCES = (
    "https://api.coingecko.com/api/v3/simple/price?ids=ethereum&vs_currencies=usd",
    "https://api.binance.com/api/v3/ticker/price?symbol=ETHUSDT",
)

CACHE_TTL = 15 * 60
_cache: dict[str, tuple[float, float]] = {}


async def eth_price_usd(session: Optional[aiohttp.ClientSession] = None) -> Optional[float]:
    """Return the ETH price in USD, or None when every source fails."""
    cached = _cache.get("eth")
    if cached and time.time() - cached[0] < CACHE_TTL:
        return cached[1]

    owns_session = session is None
    if owns_session:
        session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=6))
    assert session is not None
    try:
        for url in SOURCES:
            try:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=6)) as resp:
                    if resp.status != 200:
                        continue
                    data = await resp.json(content_type=None)
                price = _extract(data)
                if price:
                    _cache["eth"] = (time.time(), float(price))
                    return float(price)
            except (aiohttp.ClientError, ValueError, KeyError):
                continue
        return None
    finally:
        if owns_session:
            await session.close()


def _extract(data: dict) -> Optional[float]:
    """Pull the number out of either CoinGecko or Binance shaped payloads."""
    if not isinstance(data, dict):
        return None
    if "ethereum" in data and isinstance(data["ethereum"], dict):
        return data["ethereum"].get("usd")
    if "price" in data:
        return float(data["price"])
    return None


def reset_cache() -> None:
    """Drop the in-memory price (used by tests)."""
    _cache.clear()
