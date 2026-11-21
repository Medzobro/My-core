"""DigixDAO kit: on-chain arithmetic, rendering, and the HTTP surface."""

from __future__ import annotations

import asyncio
import os
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
PKG = os.path.dirname(HERE)
if PKG not in sys.path:
    sys.path.insert(0, PKG)

from audit import calldata  # noqa: E402
from audit.kit import ACID, DGD, DigixdaoKit, _collect  # noqa: E402
from audit.kit_render import render_kit, render_kit_error, render_kit_form  # noqa: E402

USER = "0xb3fee89d04d02dc4b522d487c24c810ad8e5809c"
RATE = 193_055_202
DGD_RAW = 382_981_093_740


def run(coro):
    return asyncio.run(coro)


class FakeRPC:
    def __init__(self, rate=RATE, dgd=DGD_RAW, acid=11_595 * 10**18):
        self.rate = rate
        self.dgd = dgd
        self.acid = acid
        self.calls = []

    async def call(self, chain, method, params, timeout=None):
        self.calls.append((chain, method, params))
        if method == "eth_getBalance":
            return hex(self.acid)
        if params[0]["data"].startswith("0x456a7cd8"):
            return hex(self.rate)
        if params[0]["data"].startswith("0x70a08231"):
            return hex(self.dgd)
        return "0x0"


def sample_kit(**overrides) -> DigixdaoKit:
    eth_raw = DGD_RAW * RATE
    values = dict(
        address=USER,
        rate_wei=RATE,
        dgd_raw=DGD_RAW,
        eth_raw=eth_raw,
        acid_balance_raw=11_595 * 10**18,
        steps=calldata.build_steps(
            "digixdao", contract=ACID, amount_raw=eth_raw, source_token=DGD, source_raw=DGD_RAW
        ),
        generated_at="2026-11-21T20:00:00+00:00",
    )
    values.update(overrides)
    return DigixdaoKit(**values)


def test_collect_reads_three_numbers():
    kit = run(_collect(FakeRPC(), USER))
    assert kit.rate_wei == RATE
    assert kit.dgd_raw == DGD_RAW
    assert kit.eth_raw == DGD_RAW * RATE
    assert kit.acid_balance_raw == 11_595 * 10**18
    assert kit.has_balance is True
    assert kit.solvent is True
    assert 0 < kit.coverage < 1
    assert [step["function"] for step in kit.steps] == ["approve(address,uint256)", "burn()"]


def test_collect_empty_wallet_has_no_steps():
    kit = run(_collect(FakeRPC(dgd=0), USER))
    assert kit.has_balance is False
    assert kit.steps == []
    assert kit.eth_raw == 0


def test_collect_uninitialised_contract_is_an_error():
    kit = run(_collect(FakeRPC(rate=0), USER))
    assert kit.error == "acid-not-initialised"
    assert kit.has_balance is False


def test_kit_flags_an_underfunded_pool():
    kit = run(_collect(FakeRPC(acid=1), USER))
    assert kit.solvent is False
    assert kit.coverage > 1


def test_render_contains_amount_rate_and_both_steps():
    html = render_kit(sample_kit())
    assert USER in html
    assert "73.93" in html  # ETH claim, six decimals
    assert "0.193055202" in html
    assert "approve(address,uint256)" in html
    assert "burn()" in html
    assert "0x44df8e70" in html
    assert "data-copy" in html


def test_render_empty_state_is_honest():
    html = render_kit(sample_kit(dgd_raw=0, eth_raw=0, steps=[]))
    assert "لا يوجد رصيد DGD" in html
    assert "data-copy" not in html


def test_render_escapes_an_injected_address():
    html = render_kit(sample_kit(address="<script>alert(1)</script>"))
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;" in html


def test_kit_form_and_error_render():
    assert "عدّة استرداد DGD" in render_kit_form()
    assert "form" in render_kit_form()
    assert "&lt;b&gt;" in render_kit_error("<b>boom</b>", 400)


# ---------------------------------------------------------------- HTTP layer
fastapi = pytest.importorskip("fastapi")
from audit import server  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402


@pytest.fixture()
def client(monkeypatch):
    async def fake_load(address, **kwargs):
        return sample_kit(address=address)

    monkeypatch.setattr(server, "load_kit", fake_load)
    server._hits.clear()
    return TestClient(server.app)


def test_kit_page_returns_html(client):
    response = client.get(f"/kit/digixdao/{USER}")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert USER in response.text
    assert "73.93" in response.text


def test_kit_api_returns_json(client):
    body = client.get(f"/api/kit/digixdao/{USER}").json()
    assert body["address"] == USER
    assert body["has_balance"] is True
    assert body["eth"] == pytest.approx(73.9361, abs=1e-3)
    assert body["steps"][1]["data"] == "0x44df8e70"


def test_kit_form_redirects_with_query_address(client):
    response = client.get(f"/kit/digixdao?address={USER}", follow_redirects=False)
    assert response.status_code == 307
    assert response.headers["location"] == f"/kit/digixdao/{USER}"


def test_kit_page_rejects_bad_address(monkeypatch):
    async def boom(address, **kwargs):
        raise ValueError("bad address")

    monkeypatch.setattr(server, "load_kit", boom)
    server._hits.clear()
    response = TestClient(server.app).get("/kit/digixdao/0x123")
    assert response.status_code == 400
    assert "تعذّر الفحص" in response.text
