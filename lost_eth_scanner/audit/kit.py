"""Deep recovery kit for one legacy contract: DigixDAO's Acid refund.

The generic audit answers "is anything stuck?". This kit answers the next
question for a single contract: exactly how much ETH will I get, is the pool
still solvent, and what are the bytes I sign?

Read-only. Three calls, no key, no signature.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

from core.rpc import ChainRPC, ResponseCache
from core.util import normalize_address, wei_to_float

from audit import calldata
from audit.engine import load_data

ACID = "0x23Ea10CC1e6EBdB499D24E45369A35f43627062f"
DGD = "0xe0b7927c4af23765cb51314a0e0521a9645f0e2a"
DGD_DECIMALS = 9
RATE_SELECTOR = "0x456a7cd8"  # weiPerNanoDGD()
BALANCE_SELECTOR = "0x70a08231"  # balanceOf(address)
CHAIN = "ethereum"
# keccak256(address padded) as the eth_call argument.
_ADDRESS_WORD = "0" * 24


def _hex_int(value: Any) -> int:
    if not value or value == "0x":
        return 0
    try:
        return int(value, 16)
    except (TypeError, ValueError):
        return 0


@dataclass
class DigixdaoKit:
    """Everything a DGD holder needs, read from chain state."""

    address: str
    rate_wei: int
    dgd_raw: int
    eth_raw: int
    acid_balance_raw: int
    steps: list[dict[str, Any]] = field(default_factory=list)
    generated_at: str = ""
    error: Optional[str] = None

    @property
    def dgd(self) -> float:
        return wei_to_float(self.dgd_raw, DGD_DECIMALS)

    @property
    def eth(self) -> float:
        return wei_to_float(self.eth_raw, 18)

    @property
    def acid_balance(self) -> float:
        return wei_to_float(self.acid_balance_raw, 18)

    @property
    def rate_per_dgd(self) -> float:
        return wei_to_float(self.rate_wei * 10**DGD_DECIMALS, 18)

    @property
    def coverage(self) -> float:
        """Share of the pool this claim would consume (0..1+)."""
        if self.acid_balance_raw <= 0:
            return 0.0
        return self.eth_raw / self.acid_balance_raw

    @property
    def solvent(self) -> bool:
        return self.acid_balance_raw >= self.eth_raw

    @property
    def has_balance(self) -> bool:
        return self.dgd_raw > 0 and self.rate_wei > 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "address": self.address,
            "contract": ACID,
            "token": DGD,
            "token_symbol": "DGD",
            "token_decimals": DGD_DECIMALS,
            "dgd": self.dgd,
            "dgd_raw": str(self.dgd_raw),
            "rate_wei_per_nano": self.rate_wei,
            "rate_per_dgd": self.rate_per_dgd,
            "eth": self.eth,
            "eth_raw": str(self.eth_raw),
            "acid_balance": self.acid_balance,
            "acid_balance_raw": str(self.acid_balance_raw),
            "coverage": self.coverage,
            "solvent": self.solvent,
            "has_balance": self.has_balance,
            "steps": self.steps,
            "generated_at": self.generated_at,
            "error": self.error,
        }


async def _collect(rpc: Any, address: str) -> DigixdaoKit:
    """Pure-ish collector: three reads, then arithmetic. Easy to fake in tests."""
    user = normalize_address(address)
    rate = _hex_int(
        await rpc.call(CHAIN, "eth_call", [{"to": ACID, "data": RATE_SELECTOR}, "latest"])
    )
    dgd_raw = _hex_int(
        await rpc.call(
            CHAIN,
            "eth_call",
            [{"to": DGD, "data": BALANCE_SELECTOR + _ADDRESS_WORD + user[2:]}, "latest"],
        )
    )
    acid_raw = _hex_int(await rpc.call(CHAIN, "eth_getBalance", [ACID, "latest"]))

    kit = DigixdaoKit(
        address=user,
        rate_wei=rate,
        dgd_raw=dgd_raw,
        eth_raw=dgd_raw * rate if rate > 0 else 0,
        acid_balance_raw=acid_raw,
        generated_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
    )
    if rate <= 0:
        kit.error = "acid-not-initialised"
        return kit
    if kit.eth_raw > 0:
        kit.steps = calldata.build_steps(
            "digixdao",
            contract=ACID,
            amount_raw=kit.eth_raw,
            source_token=DGD,
            source_raw=kit.dgd_raw,
        )
    return kit


async def load_kit(address: str, *, timeout: float = 10.0) -> DigixdaoKit:
    """Read the kit from public RPCs. No cache: the numbers are the point."""
    normalize_address(address)  # fail fast on a bad checksum/length
    chains_cfg, _contracts, _tokens = load_data()
    cache = ResponseCache()
    try:
        async with ChainRPC(
            chains_cfg, concurrency=4, retries=2, timeout=timeout, cache=cache
        ) as rpc:
            return await _collect(rpc, address)
    finally:
        cache.close()
