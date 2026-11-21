"""Engine tests: parsing, decimals, difficulty mapping and the full pipeline.

No network: a fake JSON-RPC object answers the calls the engine makes, so the
assertions describe real engine behaviour rather than a live chain.
"""

from __future__ import annotations

import asyncio
import os
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
PKG = os.path.dirname(HERE)
if PKG not in sys.path:
    sys.path.insert(0, PKG)

from audit import engine  # noqa: E402
from audit.engine import (  # noqa: E402  # noqa: E402
    PENDING_WITHDRAWALS_SELECTOR,
    Finding,
    Report,
    _finalize,
    _hex_int,
    _scan_contract,
    audit_address,
    load_data,
)

USER = "0x8be6ad79f67d1b76eba486b0ef4fd2c9bd1cd067"


class FakeRPC:
    """Answers eth_call by (contract, selector) and tracks every call."""

    def __init__(self, table: dict[tuple[str, str], str] | None = None, chains=None):
        self.table = {
            (str(key[0]).lower(), str(key[1]).lower()): value
            for key, value in (table or {}).items()
        }
        self.calls: list[tuple[str, str, list]] = []
        self.chains = chains or {"ethereum": {"native_token": "ETH", "rpcs": ["fake"]}}

    async def call(self, chain, method, params, timeout=None):
        self.calls.append((chain, method, params))
        if method == "eth_getBalance":
            return "0x0"
        if method != "eth_call":
            return None
        target = params[0]["to"].lower()
        data = params[0]["data"].lower()
        selector = data[:10]
        return self.table.get((target, selector))

    def stats(self):
        return {
            "rpc_calls": len(self.calls),
            "rpc_failures": 0,
            "rpc_reverts": 0,
            "failure_rate": 0.0,
        }


def contract(name: str, address: str, check: str, **extra) -> dict:
    return {"name": name, "address": address, "chain": "ethereum", "balance_check": check, **extra}


def run(coro):
    return asyncio.run(coro)


def test_hex_int_is_defensive():
    assert _hex_int(None) == 0
    assert _hex_int("0x") == 0
    assert _hex_int("0x10") == 16
    assert _hex_int("not-hex") == 0


def test_etherdelta_eth_deposit_becomes_finding():
    c = contract("ForkDelta", "0x8d12a197cb00d4747a1fe03395095ce2a5cc6819", "etherdelta")
    rpc = FakeRPC({("0x8d12a197cb00d4747a1fe03395095ce2a5cc6819", "0xf7888aec"): hex(5 * 10**18)})
    found = run(_scan_contract(rpc, c, USER, {}))
    assert found == [("ETH", 5 * 10**18, "0x" + "00" * 20, 18)]


def test_etherdelta_scans_known_tokens():
    c = contract("ForkDelta", "0x8d12a197cb00d4747a1fe03395095ce2a5cc6819", "etherdelta")
    rpc = FakeRPC()
    tokens = {
        "ethereum": {
            "0x6b175474e89094c44da98b954eedeac495271d0f": ["DAI", 18],
            "0x" + "11" * 20: ["USDC", 6],
        }
    }
    run(_scan_contract(rpc, c, USER, tokens))
    # One probe for ETH plus one probe per known token on the chain.
    assert len(rpc.calls) == 1 + len(tokens["ethereum"])


def test_erc20_self_respects_decimals():
    gst2 = contract(
        "GasToken2",
        "0x0000000000b3f879cb30fe243b4dfee438691c04",
        "erc20_self",
        balance_check_token_name="GST2",
        balance_check_token_decimals=2,
    )
    rpc = FakeRPC({("0x0000000000b3f879cb30fe243b4dfee438691c04", "0x70a08231"): hex(12345)})
    found = run(_scan_contract(rpc, gst2, USER, {}))
    assert found == [("GST2", 12345, "0x0000000000b3f879cb30fe243b4dfee438691c04", 2)]


def test_erc20_holder_uses_referenced_token():
    dao = contract(
        "WithdrawDAO",
        "0xbf4ed7b27f1d666546e30d74d50d173d20bca754",
        "erc20_holder",
        balance_check_token="0xbb9bc244d798123fde783fcc1c72d3bb8c189413",
        balance_check_token_name="DAO",
        balance_check_token_decimals=16,
    )
    rpc = FakeRPC({("0xbb9bc244d798123fde783fcc1c72d3bb8c189413", "0x70a08231"): hex(10**18)})
    found = run(_scan_contract(rpc, dao, USER, {}))
    assert found[0][0] == "DAO"
    assert found[0][3] == 16


def test_cryptopunks_uses_pending_withdrawals_selector():
    punks = contract("CryptoPunks", engine.PUNKS_CONTRACT, "cryptopunks")
    rpc = FakeRPC({(engine.PUNKS_CONTRACT, PENDING_WITHDRAWALS_SELECTOR): hex(15345 * 10**16)})
    found = run(_scan_contract(rpc, punks, USER, {}))
    assert found == [("ETH", 15345 * 10**16, "0x" + "00" * 20, 18)]
    target, _method, params = rpc.calls[0]
    assert target == "ethereum"
    assert params[0]["to"].lower() == engine.PUNKS_CONTRACT
    assert params[0]["data"].startswith(PENDING_WITHDRAWALS_SELECTOR)


def test_zero_balance_yields_nothing():
    c = contract("IDEX 1.0", "0x2a0c0dbecc7e4d658f48e01e3fa353f44050c208", "erc20_self")
    rpc = FakeRPC({("0x2a0c0dbecc7e4d658f48e01e3fa353f44050c208", "0x70a08231"): "0x0"})
    assert run(_scan_contract(rpc, c, USER, {})) == []


def _finding(
    amount: float, symbol: str = "ETH", usd: float | None = None, difficulty: str = "easy"
):
    return Finding(
        chain="ethereum",
        contract="0x1",
        contract_name="X",
        category="USER_DEPOSITS",
        symbol=symbol,
        amount=amount,
        amount_raw=int(amount * 10**18),
        token="0x0",
        check_type="etherdelta",
        difficulty=difficulty,
        title_ar="X",
        steps=[],
        usd=usd,
    )


def test_finalize_totals_and_ordering():
    report = Report(address=USER, generated_at="now")
    report.findings = [
        _finding(0.5, usd=1000.0, difficulty="hard"),
        _finding(2.0, usd=4000.0, difficulty="easy"),
        _finding(10.0, symbol="DAI"),
    ]
    _finalize(report)
    assert report.findings[0].difficulty == "easy"  # easiest first
    assert report.totals["by_symbol"] == {"ETH": 2.5, "DAI": 10.0}
    assert report.totals["usd_total"] == 5000.0
    assert "وُجد" in report.verdict_ar


def test_finalize_empty_verdict():
    report = Report(address=USER, generated_at="now")
    _finalize(report)
    assert report.totals["count"] == 0
    assert "لا يوجد" in report.verdict_ar


def test_audit_address_pipeline(monkeypatch):
    """The public entry point: fake RPC in, structured report out."""
    punks_raw = 15345 * 10**16

    class FakeSession:
        async def __aenter__(self):
            return FakeRPC({(engine.PUNKS_CONTRACT, PENDING_WITHDRAWALS_SELECTOR): hex(punks_raw)})

        async def __aexit__(self, *exc):
            return False

    monkeypatch.setattr(engine, "ChainRPC", lambda *a, **kw: FakeSession())

    async def fake_price(session=None):
        return 2000.0

    monkeypatch.setattr(engine.pricing, "eth_price_usd", fake_price)

    report = run(audit_address(USER, include_native=False))
    assert report.address == USER.lower()
    assert report.totals["count"] == 1
    assert report.findings[0].contract_name == "CryptoPunks Marketplace"
    assert report.findings[0].usd == pytest.approx(306_900.0)
    assert report.coverage["contracts_checked"] >= 13


def test_every_scanned_contract_has_guide():
    _chains, contracts, _tokens = load_data()
    assert contracts, "contract database must define at least one balance check"
    for c in contracts:
        entry = engine.guide.guide_for(c["address"], c.get("balance_check"), c["name"])
        assert entry["steps"], f"{c['name']} has no recovery steps"
        assert entry["difficulty"] in {"easy", "medium", "hard"}
        assert all("ar" not in s for s in entry["steps"])  # steps are (ar, en) tuples
