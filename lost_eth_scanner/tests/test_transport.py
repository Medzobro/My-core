"""Cache and helper tests. No sockets: only the cache and pure helpers run."""

from __future__ import annotations

import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
PKG = os.path.dirname(HERE)
if PKG not in sys.path:
    sys.path.insert(0, PKG)

from core.rpc import ChainRPC, ResponseCache  # noqa: E402
from core.util import (  # noqa: E402
    encode_addr,
    encode_uint,
    format_amount,
    normalize_address,
    short_addr,
    wei_to_float,
)


def test_cache_round_trip_and_counters():
    cache = ResponseCache(ttls={"eth_call": 60})
    assert cache.get("ethereum", "eth_call", [{"to": "0x1"}]) is None
    cache.set("ethereum", "eth_call", [{"to": "0x1"}], "0xabc")
    assert cache.get("ethereum", "eth_call", [{"to": "0x1"}]) == "0xabc"
    assert cache.hits == 1 and cache.misses == 1


def test_cache_keys_ignore_argument_order():
    a = ResponseCache.make_key("ethereum", "eth_call", [{"to": "0x1", "data": "0x2"}])
    b = ResponseCache.make_key("ethereum", "eth_call", [{"data": "0x2", "to": "0x1"}])
    assert a == b


def test_cache_respects_ttl(monkeypatch):
    cache = ResponseCache(ttls={"eth_call": 1})
    cache.set("ethereum", "eth_call", ["x"], "0x1")
    real = time.time
    monkeypatch.setattr(time, "time", lambda: real() + 5)
    assert cache.get("ethereum", "eth_call", ["x"]) is None


def test_sqlite_cache_persists(tmp_path):
    path = tmp_path / "rpc.sqlite"
    cache = ResponseCache(path=str(path))
    cache.set("ethereum", "eth_getCode", ["0x1"], "0x6060")
    cache.close()

    reopened = ResponseCache(path=str(path))
    assert reopened.get("ethereum", "eth_getCode", ["0x1"]) == "0x6060"
    reopened.close()


def test_unknown_chain_is_graceful():
    rpc = ChainRPC({}, retries=0)
    assert rpc.stats()["rpc_calls"] == 0
    assert rpc.stats()["failure_rate"] == 0.0


def test_encode_addr_pads_to_word():
    padded = encode_addr("0x8be6ad79f67d1b76eba486b0ef4fd2c9bd1cd067")
    assert len(padded) == 64
    assert padded.endswith("8be6ad79f67d1b76eba486b0ef4fd2c9bd1cd067")


def test_encode_uint():
    assert encode_uint(1) == "0" * 63 + "1"
    assert encode_uint(255) == "0" * 62 + "ff"


def test_normalize_address_rejects_junk():
    for bad in ["", "0x123", "not-an-address", "0x" + "zz" * 20, None]:
        try:
            normalize_address(bad)
        except ValueError:
            continue
        raise AssertionError(f"accepted invalid address: {bad!r}")
    assert normalize_address("0x8BE6AD79F67D1B76EBA486B0EF4FD2C9BD1CD067").startswith("0x8be6")


def test_format_helpers():
    assert format_amount(0) == "0"
    assert format_amount(1.5) == "1.5"
    assert format_amount(1234.567) == "1,234.567"
    assert wei_to_float("0xde0b6b3a7640000") == 1.0
    assert short_addr("0x8be6ad79f67d1b76eba486b0ef4fd2c9bd1cd067") == "0x8be6\u2026d067"
