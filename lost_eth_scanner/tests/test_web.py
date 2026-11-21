"""Rendering and HTTP surface tests: escaping, states, and status codes."""

from __future__ import annotations

import os
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
PKG = os.path.dirname(HERE)
if PKG not in sys.path:
    sys.path.insert(0, PKG)

from audit.engine import Finding, Report  # noqa: E402
from audit.render import render_error, render_report  # noqa: E402

USER = "0x8be6ad79f67d1b76eba486b0ef4fd2c9bd1cd067"


def sample_report(**overrides) -> Report:
    finding = Finding(
        chain="ethereum",
        contract="0xb47e3cd837ddf8e4c57f05d70ab865de6e193bbb",
        contract_name="CryptoPunks Marketplace",
        category="USER_DEPOSITS",
        symbol="ETH",
        amount=153.45,
        amount_raw=15345 * 10**16,
        token="0x" + "00" * 20,
        check_type="cryptopunks",
        difficulty="easy",
        title_ar="CryptoPunks",
        steps=[{"ar": "افتح العقد", "en": "Open the contract"}],
        usd=306900.0,
        withdraw_method="withdraw()",
    )
    report = Report(
        address=USER,
        generated_at="2026-11-21T10:00:00+00:00",
        findings=[finding],
        native=[{"chain": "ethereum", "symbol": "ETH", "amount": 0.5, "amount_raw": "500"}],
        totals={
            "by_symbol": {"ETH": 153.45},
            "usd_total": 306900.0,
            "count": 1,
            "eth_equivalent": 153.45,
        },
        coverage={"contracts_checked": 13, "chains_available": 9, "chains_scanned": ["ethereum"]},
        stats={"rpc_calls": 273, "rpc_failures": 0, "rpc_reverts": 39, "failure_rate": 0.0},
        eth_usd=2000.0,
        elapsed=3.1,
        verdict_ar="وُجد 1 رصيداً قابلاً للاسترداد.",
        verdict_en="Found 1 balance.",
    )
    for key, value in overrides.items():
        setattr(report, key, value)
    return report


def test_report_contains_core_facts():
    html = render_report(sample_report())
    assert USER in html
    assert "CryptoPunks Marketplace" in html
    assert "153.45 ETH" in html
    assert "افتح العقد" in html
    assert "├" not in html
    assert html.count("<html") == 1


def test_report_escapes_untrusted_text():
    report = sample_report()
    report.findings[0].contract_name = "<script>alert(1)</script>"
    report.findings[0].steps = [{"ar": "<img src=x onerror=alert(2)>", "en": "ok"}]
    html = render_report(report)
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;" in html
    assert "<img src=x" not in html


def test_empty_report_renders_empty_state():
    report = sample_report()
    report.findings = []
    report.native = []
    report.totals = {"by_symbol": {}, "usd_total": None, "count": 0, "eth_equivalent": 0.0}
    report.verdict_ar = "لا يوجد رصيد عالق."
    html = render_report(report)
    assert "لا شيء لعرضه" in html
    assert "CryptoPunks" not in html


def test_error_page_escapes_message():
    html = render_error("<b>boom</b>", 400)
    assert "&lt;b&gt;boom&lt;/b&gt;" in html


# ---------------------------------------------------------------- HTTP layer
fastapi = pytest.importorskip("fastapi")
from audit import server  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402


@pytest.fixture()
def client(monkeypatch):
    async def fake_audit(address, **kwargs):
        return sample_report()

    monkeypatch.setattr(server, "audit_address", fake_audit)
    server._reports.clear()
    server._hits.clear()
    return TestClient(server.app)


def test_api_audit_returns_json(client):
    response = client.post("/api/audit", json={"address": USER})
    assert response.status_code == 200
    body = response.json()
    assert body["address"] == USER
    assert body["totals"]["count"] == 1
    assert body["findings"][0]["symbol"] == "ETH"


def test_api_audit_rejects_bad_address(client):
    response = client.post("/api/audit", json={"address": "0x123"})
    assert response.status_code == 400
    assert "detail" in response.json()


def test_api_audit_is_cached(client):
    client.post("/api/audit", json={"address": USER})
    second = client.post("/api/audit", json={"address": USER})
    assert second.json()["cached"] is True


def test_report_route_returns_html(client):
    response = client.get(f"/report/{USER}")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert USER in response.text


def test_health_and_stats(client):
    assert client.get("/health").json()["status"] == "ok"
    assert "contracts_in_db" in client.get("/api/stats").json()


def test_landing_page_served(client):
    response = client.get("/")
    assert response.status_code == 200
    assert "مستحقاتي" in response.text


def test_security_headers_present(client):
    response = client.get("/")
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
    assert "default-src 'self'" in response.headers["content-security-policy"]
    assert len(response.headers["x-request-id"]) == 12


def test_rate_limit_blocks_after_quota(client, monkeypatch):
    monkeypatch.setattr(server, "RATE_LIMIT", 3)
    codes = [client.post("/api/audit", json={"address": USER}).status_code for _ in range(4)]
    assert codes[:3] == [200, 200, 200]
    assert codes[3] == 429


def test_client_ip_ignores_forwarded_header_by_default(monkeypatch):
    class FakeRequest:
        headers = {"x-forwarded-for": "1.2.3.4, 10.0.0.1"}
        client = type("C", (), {"host": "9.9.9.9"})()

    monkeypatch.setattr(server, "TRUST_PROXY", False)
    assert server._client_ip(FakeRequest()) == "9.9.9.9"
    monkeypatch.setattr(server, "TRUST_PROXY", True)
    assert server._client_ip(FakeRequest()) == "1.2.3.4"
