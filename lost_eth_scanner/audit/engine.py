"""Audit engine: turn one address into a structured, honest report.

The engine only reads public chain state for the address the visitor supplies.
It never signs, never asks for a key, and never probes contracts the visitor is
not a party to.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

HERE = os.path.dirname(os.path.abspath(__file__))
PKG = os.path.dirname(HERE)
for path in (PKG, HERE):
    if path not in sys.path:
        sys.path.insert(0, path)

from core import pricing  # noqa: E402
from core.rpc import ChainRPC, ResponseCache  # noqa: E402
from core.util import (  # noqa: E402
    ZERO_ADDRESS,
    encode_addr,
    normalize_address,
    wei_to_float,
)

from audit import guide  # noqa: E402

DATA_DIR = os.path.join(PKG, "data")
PUNKS_CONTRACT = "0xb47e3cd837ddf8e4c57f05d70ab865de6e193bbb"
# keccak256("pendingWithdrawals(address)")[:4]
PENDING_WITHDRAWALS_SELECTOR = "0xf3f43703"

DIFFICULTY_RANK = {"easy": 0, "medium": 1, "hard": 2}


@dataclass
class Finding:
    """One recoverable balance tied to the audited address."""

    chain: str
    contract: str
    contract_name: str
    category: str
    symbol: str
    amount: float
    amount_raw: int
    token: str
    check_type: str
    difficulty: str
    title_ar: str
    steps: list[dict[str, str]]
    note_ar: Optional[str] = None
    note_en: Optional[str] = None
    withdraw_method: Optional[str] = None
    usd: Optional[float] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "chain": self.chain,
            "contract": self.contract,
            "contract_name": self.contract_name,
            "category": self.category,
            "symbol": self.symbol,
            "amount": self.amount,
            "amount_raw": str(self.amount_raw),
            "token": self.token,
            "check_type": self.check_type,
            "difficulty": self.difficulty,
            "title_ar": self.title_ar,
            "steps": self.steps,
            "note_ar": self.note_ar,
            "note_en": self.note_en,
            "withdraw_method": self.withdraw_method,
            "usd": self.usd,
            "etherscan": guide.etherscan_url(self.contract, is_token=False),
        }


@dataclass
class Report:
    address: str
    generated_at: str
    findings: list[Finding] = field(default_factory=list)
    native: list[dict[str, Any]] = field(default_factory=list)
    totals: dict[str, Any] = field(default_factory=dict)
    coverage: dict[str, Any] = field(default_factory=dict)
    stats: dict[str, Any] = field(default_factory=dict)
    eth_usd: Optional[float] = None
    elapsed: float = 0.0
    verdict_ar: str = ""
    verdict_en: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "address": self.address,
            "generated_at": self.generated_at,
            "findings": [f.to_dict() for f in self.findings],
            "native": self.native,
            "totals": self.totals,
            "coverage": self.coverage,
            "stats": self.stats,
            "eth_usd": self.eth_usd,
            "elapsed": round(self.elapsed, 2),
            "verdict_ar": self.verdict_ar,
            "verdict_en": self.verdict_en,
        }


# --------------------------------------------------------------------------
# data + individual checks
# --------------------------------------------------------------------------
def load_data(data_dir: str = DATA_DIR) -> tuple[dict, list[dict], dict]:
    """Load chains, contracts and tokens from the JSON databases."""
    with open(os.path.join(data_dir, "chains.json"), encoding="utf-8") as fh:
        chains = json.load(fh)["chains"]
    with open(os.path.join(data_dir, "contracts_multichain.json"), encoding="utf-8") as fh:
        raw = json.load(fh)["contracts"]
    contracts = [c for c in raw if c.get("address", "").startswith("0x") and c.get("balance_check")]
    tokens: dict[str, dict] = {}
    token_file = os.path.join(data_dir, "tokens_multichain.json")
    if os.path.exists(token_file):
        with open(token_file, encoding="utf-8") as fh:
            for chain, table in json.load(fh).items():
                if chain.startswith("_") or not isinstance(table, dict):
                    continue
                tokens[chain] = {
                    addr.split("_")[0]: meta
                    for addr, meta in table.items()
                    if addr.startswith("0x") and len(addr.split("_")[0]) == 42
                }
    return chains, contracts, tokens


async def _erc20_balance(rpc: ChainRPC, chain: str, token: str, holder: str) -> int:
    data = "0x70a08231" + encode_addr(holder)
    res = await rpc.call(chain, "eth_call", [{"to": token, "data": data}, "latest"])
    return _hex_int(res)


async def _dex_deposit(rpc: ChainRPC, chain: str, contract: str, user: str, token: str) -> int:
    """EtherDelta-style ``tokens[token][user]`` mapping."""
    data = "0xf7888aec" + encode_addr(token) + encode_addr(user)
    res = await rpc.call(chain, "eth_call", [{"to": contract, "data": data}, "latest"])
    return _hex_int(res)


def _hex_int(value: Any) -> int:
    if not value or value == "0x":
        return 0
    try:
        return int(value, 16)
    except (TypeError, ValueError):
        return 0


async def _scan_contract(
    rpc: ChainRPC, contract: dict, user: str, tokens_db: dict
) -> list[tuple[str, int, str, int]]:
    """Return (symbol, raw_amount, token_address, decimals) for one contract."""
    chain = contract["chain"]
    address = contract["address"]
    check = contract.get("balance_check")
    found: list[tuple[str, int, str, int]] = []

    if check == "etherdelta":
        raw = await _dex_deposit(rpc, chain, address, user, ZERO_ADDRESS)
        if raw > 0:
            found.append(("ETH", raw, ZERO_ADDRESS, 18))
        for token_addr, meta in tokens_db.get(chain, {}).items():
            symbol, decimals = meta[0], int(meta[1])
            raw = await _dex_deposit(rpc, chain, address, user, token_addr)
            if raw > 0:
                found.append((symbol, raw, token_addr, decimals))

    elif check == "erc20_self":
        raw = await _erc20_balance(rpc, chain, address, user)
        if raw > 0:
            decimals = int(contract.get("balance_check_token_decimals", 18))
            symbol = contract.get("balance_check_token_name") or contract["name"][:12]
            found.append((symbol, raw, address, decimals))

    elif check == "erc20_holder":
        token = contract.get("balance_check_token")
        if token:
            raw = await _erc20_balance(rpc, chain, token, user)
            if raw > 0:
                decimals = int(contract.get("balance_check_token_decimals", 18))
                symbol = contract.get("balance_check_token_name", "TOKEN")
                found.append((symbol, raw, token, decimals))

    elif check == "cryptopunks":
        data = PENDING_WITHDRAWALS_SELECTOR + encode_addr(user)
        res = await rpc.call(chain, "eth_call", [{"to": PUNKS_CONTRACT, "data": data}, "latest"])
        raw = _hex_int(res)
        if raw > 0:
            found.append(("ETH", raw, ZERO_ADDRESS, 18))

    return found


async def _native_balances(rpc: ChainRPC, chains: list[str], user: str) -> list[dict]:
    async def one(chain: str) -> Optional[dict]:
        res = await rpc.call(chain, "eth_getBalance", [user, "latest"])
        raw = _hex_int(res)
        if raw <= 0:
            return None
        symbol = rpc.chains.get(chain, {}).get("native_token", "ETH")
        return {
            "chain": chain,
            "symbol": symbol,
            "amount": wei_to_float(raw, 18),
            "amount_raw": str(raw),
        }

    results = await asyncio.gather(*(one(c) for c in chains), return_exceptions=True)
    return [r for r in results if isinstance(r, dict)]


# --------------------------------------------------------------------------
# public API
# --------------------------------------------------------------------------
async def audit_address(
    address: str,
    *,
    chains_filter: Optional[list[str]] = None,
    include_native: bool = True,
    cache_path: Optional[str] = None,
    concurrency: int = 40,
    retries: int = 2,
    timeout: float = 8.0,
) -> Report:
    """Scan ``address`` against every known stuck-fund contract."""
    started = time.perf_counter()
    user = normalize_address(address)
    chains_cfg, contracts, tokens_db = load_data()

    if chains_filter:
        wanted = {c.strip().lower() for c in chains_filter if c.strip()}
        contracts = [c for c in contracts if c["chain"] in wanted]
        chains = [c for c in chains_cfg if c in wanted]
    else:
        chains = list(chains_cfg)

    cache = ResponseCache(path=cache_path) if cache_path else ResponseCache()
    report = Report(
        address=user,
        generated_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        coverage={
            "contracts_checked": len(contracts),
            "chains_available": len(chains_cfg),
            "chains_scanned": sorted({c["chain"] for c in contracts}),
        },
    )

    async with ChainRPC(
        chains_cfg, concurrency=concurrency, retries=retries, timeout=timeout, cache=cache
    ) as rpc:
        scans = await asyncio.gather(
            *(_scan_contract(rpc, c, user, tokens_db) for c in contracts),
            return_exceptions=True,
        )
        price = await pricing.eth_price_usd()
        report.eth_usd = price

        for contract, result in zip(contracts, scans, strict=False):
            if isinstance(result, BaseException):
                continue
            for symbol, raw, token_addr, decimals in result:
                entry = guide.guide_for(
                    contract["address"], contract.get("balance_check"), contract["name"]
                )
                amount = wei_to_float(raw, decimals)
                usd = round(amount * price, 2) if price and symbol == "ETH" else None
                report.findings.append(
                    Finding(
                        chain=contract["chain"],
                        contract=contract["address"],
                        contract_name=contract["name"],
                        category=contract.get("category", ""),
                        symbol=symbol,
                        amount=amount,
                        amount_raw=raw,
                        token=token_addr,
                        check_type=contract.get("balance_check", ""),
                        difficulty=entry.get("difficulty", "medium"),
                        title_ar=entry.get("title_ar", contract["name"]),
                        steps=[{"ar": ar, "en": en} for ar, en in entry.get("steps", [])],
                        note_ar=entry.get("note_ar"),
                        note_en=entry.get("note_en"),
                        withdraw_method=contract.get("withdraw_method"),
                        usd=usd,
                    )
                )

        if include_native:
            report.native = await _native_balances(rpc, chains, user)

        report.stats = rpc.stats()

    cache.close()
    _finalize(report)
    report.elapsed = time.perf_counter() - started
    return report


def _finalize(report: Report) -> None:
    """Sort findings and compute totals + verdicts."""
    report.findings.sort(
        key=lambda f: (DIFFICULTY_RANK.get(f.difficulty, 9), -(f.usd or 0), -f.amount)
    )

    by_symbol: dict[str, float] = {}
    for finding in report.findings:
        by_symbol[finding.symbol] = by_symbol.get(finding.symbol, 0.0) + finding.amount

    usd_total = sum(f.usd or 0 for f in report.findings if f.usd)
    eth_like = by_symbol.get("ETH", 0.0)

    report.totals = {
        "by_symbol": {k: round(v, 8) for k, v in by_symbol.items()},
        "usd_total": round(usd_total, 2) if usd_total else None,
        "count": len(report.findings),
        "eth_equivalent": round(eth_like, 8),
    }

    if report.findings:
        symbols = ", ".join(f"{v:,.4f} {k}".rstrip("0").rstrip(".") for k, v in by_symbol.items())
        value = f" (~${usd_total:,.0f})" if usd_total else ""
        report.verdict_en = (
            f"Found {len(report.findings)} recoverable balance(s): {symbols}{value}."
        )
        report.verdict_ar = f"وُجد {len(report.findings)} رصيداً قابلاً للاسترداد: {symbols}{value}."
    else:
        report.verdict_ar = "لا يوجد رصيد عالق في العقود المعروفة لهذا العنوان."
        report.verdict_en = "No stuck balance found in the known contracts for this address."


def audit_address_sync(address: str, **kwargs: Any) -> Report:
    """Blocking wrapper for scripts and the CLI."""
    return asyncio.run(audit_address(address, **kwargs))
