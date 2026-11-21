"""Calldata builder tests: pinned selectors, ABI words and DGD two-step flow."""

from __future__ import annotations

import os
import sys

import pytest
from Crypto.Hash import keccak

HERE = os.path.dirname(os.path.abspath(__file__))
PKG = os.path.dirname(HERE)
if PKG not in sys.path:
    sys.path.insert(0, PKG)

from audit import calldata  # noqa: E402
from audit.engine import load_data  # noqa: E402

ACID = "0x23ea10cc1e6ebdb499d24e45369a35f43627062f"
DGD = "0xe0b7927c4af23765cb51314a0e0521a9645f0e2a"
ZERO = "0x0000000000000000000000000000000000000000"


def test_every_selector_matches_keccak():
    """A selector is never typed from memory: recompute every pinned value."""
    for signature, pinned in calldata.SELECTORS.items():
        digest = keccak.new(digest_bits=256)
        digest.update(signature.encode())
        assert "0x" + digest.hexdigest()[:8] == pinned, signature


def test_address_and_uint_encoding():
    assert calldata.encode_address(ACID) == "0" * 24 + ACID[2:]
    assert calldata.encode_uint(1) == "0" * 63 + "1"
    with pytest.raises(ValueError):
        calldata.encode_address("0x123")
    with pytest.raises(ValueError):
        calldata.encode_uint(-1)


def test_withdraw_eth_calldata_is_exact():
    steps = calldata.build_steps(
        "etherdelta",
        contract="0x8d12a197cb00d4747a1fe03395095ce2a5cc6819",
        token=ZERO,
        amount_raw=10**18,
    )
    assert steps == [
        {
            "function": "withdraw(uint256)",
            "to": "0x8d12a197cb00d4747a1fe03395095ce2a5cc6819",
            "data": "0x2e1a7d4d" + "0" * 49 + "de0b6b3a7640000",
            "value": "0x0",
            "label_ar": steps[0]["label_ar"],
            "label_en": steps[0]["label_en"],
        }
    ]


def test_withdraw_token_uses_token_then_amount():
    steps = calldata.build_steps(
        "idex",
        contract="0x2a0c0dbecc7e4d658f48e01e3fa353f44050c208",
        token="0x6b175474e89094c44da98b954eedeac495271d0f",
        amount_raw=2,
    )
    assert steps[0]["data"] == (
        "0xf3fef3a3" + "0" * 24 + "6b175474e89094c44da98b954eedeac495271d0f" + "0" * 63 + "2"
    )


def test_digixdao_is_two_steps_and_reads_the_acid_contract():
    steps = calldata.build_steps(
        "digixdao",
        contract=ACID,
        amount_raw=73930000000000000000,
        source_token=DGD,
        source_raw=382981093740,
    )
    assert [step["function"] for step in steps] == ["approve(address,uint256)", "burn()"]
    assert steps[0]["to"] == DGD
    assert steps[0]["data"].startswith("0x095ea7b3" + "0" * 24 + ACID[2:])
    assert steps[0]["data"].endswith(f"{382981093740:064x}")
    assert steps[1]["to"] == ACID
    assert steps[1]["data"] == "0x44df8e70"


def test_unknown_or_empty_kind_yields_no_steps():
    assert calldata.build_steps(None, contract=ACID) == []
    assert calldata.build_steps("none", contract=ACID) == []
    with pytest.raises(ValueError):
        calldata.build_steps("made-up", contract=ACID)


def test_every_configured_contract_builds_steps():
    """Data and code cannot drift: every calldata_kind in the DB must work."""
    _chains, contracts, _tokens = load_data()
    for contract in contracts:
        kind = contract.get("calldata_kind")
        if not kind or kind == "none":
            continue
        steps = calldata.build_steps(
            kind,
            contract=contract["address"],
            token=contract.get("balance_check_token") or ZERO,
            amount_raw=1,
            source_token=contract.get("balance_check_token") or DGD,
            source_raw=1,
        )
        assert steps, contract["name"]
