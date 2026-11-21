"""JSON-RPC transport: multi-endpoint fallback, retry/backoff, TTL cache.

Every call the scanner makes is read-only (``eth_call``, ``eth_getBalance``,
``eth_getCode``) against public RPC endpoints. A revert is a legitimate answer
and is reported as ``None``; a transport failure is counted separately so a
report can state how much of the scan actually succeeded.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import sqlite3
import threading
import time
from typing import Any, Optional

import aiohttp

# Per-method cache lifetimes in seconds. Chain state moves; bytecode does not.
DEFAULT_TTLS: dict[str, int] = {
    "eth_getCode": 7 * 24 * 3600,
    "eth_call": 120,
    "eth_getBalance": 30,
    "eth_blockNumber": 2,
    "eth_chainId": 7 * 24 * 3600,
}

USER_AGENT = "lost-eth-audit/1.0 (+https://github.com/Medzobro/My-core)"


class ResponseCache:
    """SQLite-backed TTL cache shared by every RPC call in a process.

    Keyed deterministically by (chain, method, params). Without a path the
    cache is memory-only, which is what the tests use.
    """

    def __init__(self, path: Optional[str] = None, ttls: Optional[dict[str, int]] = None):
        self.ttls = {**DEFAULT_TTLS, **(ttls or {})}
        self._mem: dict[str, tuple[float, Any]] = {}
        self._lock = threading.Lock()
        self.hits = 0
        self.misses = 0
        self._conn: Optional[sqlite3.Connection] = None
        if path:
            parent = os.path.dirname(os.path.abspath(path))
            if parent:
                os.makedirs(parent, exist_ok=True)
            self._conn = sqlite3.connect(path, check_same_thread=False)
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute(
                "CREATE TABLE IF NOT EXISTS rpc_cache ("
                " key TEXT PRIMARY KEY, value TEXT NOT NULL, stored_at REAL NOT NULL)"
            )
            self._conn.commit()

    @staticmethod
    def make_key(chain: str, method: str, params: list) -> str:
        blob = json.dumps([chain, method, params], sort_keys=True, default=str)
        return hashlib.sha256(blob.encode()).hexdigest()

    def get(self, chain: str, method: str, params: list) -> Optional[Any]:
        key = self.make_key(chain, method, params)
        ttl = self.ttls.get(method, 60)
        now = time.time()
        with self._lock:
            cached = self._mem.get(key)
            if cached and now - cached[0] < ttl:
                self.hits += 1
                return cached[1]
            if self._conn is not None:
                row = self._conn.execute(
                    "SELECT value, stored_at FROM rpc_cache WHERE key = ?", (key,)
                ).fetchone()
                if row and now - row[1] < ttl:
                    try:
                        value = json.loads(row[0])
                    except json.JSONDecodeError:
                        value = None
                    if value is not None:
                        self.hits += 1
                        self._mem[key] = (row[1], value)
                        return value
        self.misses += 1
        return None

    def set(self, chain: str, method: str, params: list, value: Any) -> None:
        if value is None:
            return
        key = self.make_key(chain, method, params)
        now = time.time()
        with self._lock:
            self._mem[key] = (now, value)
            if len(self._mem) > 50_000:  # keep the in-process map bounded
                stale = sorted(self._mem, key=lambda k: self._mem[k][0])[:10_000]
                for doomed in stale:
                    self._mem.pop(doomed, None)
            if self._conn is not None:
                self._conn.execute(
                    "INSERT OR REPLACE INTO rpc_cache (key, value, stored_at) VALUES (?, ?, ?)",
                    (key, json.dumps(value), now),
                )
                self._conn.commit()

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None


class ChainRPC:
    """Async JSON-RPC client with per-chain endpoint rotation and retries.

    ``call`` matches the older ``MultiRPC`` surface (``.chains``, ``.calls``,
    ``.fails``) so existing scanner modules keep working unchanged.
    """

    def __init__(
        self,
        chains: dict[str, dict],
        *,
        concurrency: int = 40,
        retries: int = 2,
        timeout: float = 8.0,
        cache: Optional[ResponseCache] = None,
    ):
        self.chains = chains
        self.retries = retries
        self.timeout = timeout
        self.semaphore = asyncio.Semaphore(concurrency)
        self.cache = cache
        self.calls = 0
        self.fails = 0
        self.reverts = 0
        self.failures_by_chain: dict[str, int] = {}
        self._session: Optional[aiohttp.ClientSession] = None

    async def __aenter__(self) -> "ChainRPC":
        await self.start()
        return self

    async def __aexit__(self, *exc_info) -> None:
        await self.close()

    async def start(self) -> None:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                connector=aiohttp.TCPConnector(limit=64, ttl_dns_cache=300),
                timeout=aiohttp.ClientTimeout(total=self.timeout),
                headers={"User-Agent": USER_AGENT},
            )

    async def close(self) -> None:
        if self._session is not None and not self._session.closed:
            await self._session.close()
        self._session = None

    async def call(
        self,
        chain: str,
        method: str,
        params: list,
        timeout: Optional[float] = None,
    ) -> Optional[Any]:
        """Call ``method`` on ``chain``. Returns the JSON-RPC result, else None."""
        if self._session is None:
            await self.start()
        assert self._session is not None

        if self.cache is not None:
            cached = self.cache.get(chain, method, params)
            if cached is not None:
                return cached

        chain_cfg = self.chains.get(chain)
        if not chain_cfg or not chain_cfg.get("rpcs"):
            return None

        payload = {"jsonrpc": "2.0", "method": method, "params": params, "id": 1}
        attempt_budget = self.retries + 1

        for attempt in range(attempt_budget):
            for endpoint in chain_cfg["rpcs"]:
                data: dict[str, Any] = {}
                async with self.semaphore:
                    self.calls += 1
                    try:
                        async with self._session.post(
                            endpoint,
                            json=payload,
                            timeout=aiohttp.ClientTimeout(total=timeout or self.timeout),
                        ) as resp:
                            if resp.status == 429:
                                await asyncio.sleep(0.25 * (attempt + 1))
                                continue
                            if resp.status != 200:
                                continue
                            data = await resp.json(content_type=None)
                    except (aiohttp.ClientError, asyncio.TimeoutError, ValueError):
                        continue

                if data.get("result") is not None:
                    result = data["result"]
                    if self.cache is not None:
                        self.cache.set(chain, method, params, result)
                    return result
                if "error" in data:
                    self.reverts += 1
                    return None

            # The whole endpoint ring failed; back off before trying again.
            self.fails += 1
            self.failures_by_chain[chain] = self.failures_by_chain.get(chain, 0) + 1
            if attempt + 1 < attempt_budget:
                await asyncio.sleep(min(0.4 * (2**attempt), 2.0))

        return None

    def stats(self) -> dict[str, Any]:
        total = max(self.calls, 1)
        return {
            "rpc_calls": self.calls,
            "rpc_failures": self.fails,
            "rpc_reverts": self.reverts,
            "failure_rate": round(self.fails / total, 4),
            "failures_by_chain": dict(self.failures_by_chain),
            "cache": (
                {"hits": self.cache.hits, "misses": self.cache.misses}
                if self.cache is not None
                else {"hits": 0, "misses": 0}
            ),
        }
