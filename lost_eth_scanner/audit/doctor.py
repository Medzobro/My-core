"""Database health check.

The weakest part of a tool like this is its data: a database entry can point at a
contract that was destroyed, migrated, or never existed. ``doctor`` walks every
scanned contract, fetches its bytecode and reports what it actually finds.

Advisory, not authoritative: a missing selector in bytecode can also mean the
dispatcher compares masked words (solidity >= 0.6) instead of literal PUSH4s.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any, Optional

from core.rpc import ChainRPC, ResponseCache

from audit.engine import load_data

# keccak256(signature)[:4], computed offline and pinned here.
SELECTORS: dict[str, str] = {
    "0x3ccfd60b": "withdraw()",
    "0x2e1a7d4d": "withdraw(uint256)",
    "0xf3fef3a3": "withdraw(address,uint256)",
    "0x9e281a98": "withdrawToken(address,uint256)",
    "0xf3f43703": "pendingWithdrawals(address)",
    "0xdb006a75": "redeem(uint256)",
    "0x42966c68": "burn(uint256)",
    "0x44df8e70": "burn()",
    "0x456a7cd8": "weiPerNanoDGD()",
    "0xd8ccd0f3": "free(uint256)",
    "0x70a08231": "balanceOf(address)",
    "0xf7888aec": "balanceOf(address,address)",
    "0x508493bc": "tokens(address,address)",
}

EXPECTED_SELECTOR: dict[str, str] = {
    "etherdelta": "0xf7888aec",
    "erc20_self": "0x70a08231",
    "erc20_holder": "0x70a08231",
    "cryptopunks": "0xf3f43703",
    "digixdao": "0x44df8e70",
}


@dataclass
class ContractHealth:
    name: str
    address: str
    chain: str
    check_type: str
    code_bytes: int = 0
    is_contract: bool = False
    selectors_found: list[str] = field(default_factory=list)
    expected_found: Optional[bool] = None
    note: str = ""


def analyse(
    name: str, address: str, chain: str, check_type: str, code: Optional[str]
) -> ContractHealth:
    """Pure function: bytecode -> health verdict (no network, easy to test)."""
    health = ContractHealth(name=name, address=address, chain=chain, check_type=check_type)
    if not code or code in {"0x", "0x0"}:
        health.note = "no bytecode: destroyed, migrated, or wrong address"
        return health

    body = code.lower()[2:]
    health.code_bytes = len(body) // 2
    health.is_contract = health.code_bytes > 0
    if not health.is_contract:
        health.note = "empty code"
        return health

    for selector, signature in SELECTORS.items():
        if selector[2:] in body:
            health.selectors_found.append(signature)

    expected = EXPECTED_SELECTOR.get(check_type)
    if expected:
        health.expected_found = expected[2:] in body
        if not health.expected_found:
            health.note = (
                "expected selector missing - could be a proxy, masked dispatch, or a stale entry"
            )
    return health


async def doctor(*, cache_path: Optional[str] = None, concurrency: int = 10) -> dict[str, Any]:
    """Check every scanned contract against live chain state."""
    chains_cfg, contracts, _tokens = load_data()
    cache = ResponseCache(path=cache_path) if cache_path else ResponseCache()
    results: list[ContractHealth] = []

    async with ChainRPC(
        chains_cfg, concurrency=concurrency, retries=1, timeout=10.0, cache=cache
    ) as rpc:
        codes = await asyncio.gather(
            *(rpc.call(c["chain"], "eth_getCode", [c["address"], "latest"]) for c in contracts),
            return_exceptions=True,
        )

    for contract, code in zip(contracts, codes, strict=False):
        if isinstance(code, BaseException):
            code = None
        results.append(
            analyse(
                contract["name"],
                contract["address"],
                contract["chain"],
                contract.get("balance_check", ""),
                code if isinstance(code, str) else None,
            )
        )

    cache.close()
    dead = [r for r in results if not r.is_contract]
    missing_selector = [r for r in results if r.expected_found is False]
    return {
        "checked": len(results),
        "healthy": len(results) - len(dead),
        "dead": len(dead),
        "selector_warnings": len(missing_selector),
        "contracts": [r.__dict__ for r in results],
    }
