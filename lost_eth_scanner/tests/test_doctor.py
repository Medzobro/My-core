"""Doctor tests: pure bytecode analysis plus the CLI wiring."""

from __future__ import annotations

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PKG = os.path.dirname(HERE)
if PKG not in sys.path:
    sys.path.insert(0, PKG)

from audit.doctor import SELECTORS, analyse  # noqa: E402

ADDRESS = "0x8d12a197cb00d4747a1fe03395095ce2a5cc6819"


def test_missing_code_is_reported_as_dead():
    health = analyse("ForkDelta", ADDRESS, "ethereum", "etherdelta", "0x")
    assert health.is_contract is False
    assert health.code_bytes == 0
    assert "no bytecode" in health.note


def test_none_code_is_reported_as_dead():
    health = analyse("X", ADDRESS, "ethereum", "etherdelta", None)
    assert health.is_contract is False


def test_selectors_are_detected_in_bytecode():
    body = "6080604052" + "63" + "70a08231" + "63" + "3ccfd60b" + "00"
    health = analyse("X", ADDRESS, "ethereum", "erc20_self", "0x" + body)
    assert health.is_contract is True
    assert health.code_bytes == len(body) // 2
    assert "balanceOf(address)" in health.selectors_found
    assert "withdraw()" in health.selectors_found
    assert health.expected_found is True


def test_proxy_without_expected_selector_warns():
    # A minimal-proxy style body: no balanceOf in the runtime code.
    body = "363d3d373d3d3d363d73" + "11" * 20 + "5af43d82803e903d91602b57fd5bf3"
    health = analyse("Proxy", ADDRESS, "ethereum", "erc20_self", "0x" + body)
    assert health.is_contract is True
    assert health.expected_found is False
    assert "proxy" in health.note


def test_all_pinned_selectors_look_like_selectors():
    assert len(SELECTORS) >= 8
    for selector, signature in SELECTORS.items():
        assert selector.startswith("0x") and len(selector) == 10
        assert "(" in signature and signature.endswith(")")
