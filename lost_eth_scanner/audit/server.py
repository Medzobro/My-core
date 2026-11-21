"""FastAPI surface for the stuck-funds audit.

Endpoints
---------
GET  /                 landing page
POST /api/audit        {"address": "0x.."} -> JSON report
GET  /report/{addr}    server-rendered HTML report (shareable)
GET  /health           liveness + cache counters
GET  /api/stats        aggregate numbers for the landing page
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
import uuid
from collections import deque
from typing import Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import (
    FileResponse,
    HTMLResponse,
    JSONResponse,
    RedirectResponse,
    Response,
)
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator

from audit.engine import Report, audit_address, load_data
from audit.kit import load_kit
from audit.kit_render import render_kit, render_kit_error, render_kit_form
from audit.render import render_error, render_report

HERE = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(HERE, "static")
CONTRACTS_IN_DB = len(load_data()[1])

REPORT_TTL = 600
MAX_CACHED = 500
MAX_CLIENTS = 10_000
SCAN_TIMEOUT = 45.0
RATE_LIMIT = 20
RATE_WINDOW = 300.0
TRUST_PROXY = os.environ.get("TRUST_PROXY", "").lower() in {"1", "true", "yes"}

security_log = logging.getLogger("mustahaqati.security")

app = FastAPI(title="Mustahaqati — Stuck Funds Audit", version="1.0.0")
if os.path.isdir(STATIC_DIR):
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

_reports: dict[str, tuple[float, Report]] = {}
_hits: dict[str, deque] = {}
_served = {"audits": 0, "findings": 0}


@app.middleware("http")
async def _security_and_timing(request: Request, call_next):
    """Attach hardening headers and log one line per request with its latency."""
    request_id = uuid.uuid4().hex[:12]
    started = time.perf_counter()
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
        "font-src 'self' https://fonts.gstatic.com; "
        "script-src 'self'; img-src 'self' data:; connect-src 'self'; "
        "frame-ancestors 'none'"
    )
    elapsed_ms = (time.perf_counter() - started) * 1000
    security_log.info(
        "%s %s %s %d %.0fms",
        request_id,
        request.method,
        request.url.path,
        response.status_code,
        elapsed_ms,
    )
    return response


class AuditRequest(BaseModel):
    address: str = Field(..., min_length=42, max_length=42)
    chains: Optional[list[str]] = None
    include_native: bool = True

    @field_validator("address")
    @classmethod
    def _check_address(cls, value: str) -> str:
        value = value.strip()
        if not (value.startswith("0x") and len(value) == 42):
            raise ValueError("address must be 0x followed by 40 hex characters")
        int(value[2:], 16)  # raises for non-hex input
        return value.lower()


def _client_ip(request: Request) -> str:
    """Best-effort client identity for rate limiting.

    X-Forwarded-For is only honoured when TRUST_PROXY is set, because the header
    is trivially spoofed on a directly exposed server.
    """
    if TRUST_PROXY:
        forwarded = request.headers.get("x-forwarded-for", "")
        if forwarded:
            return forwarded.split(",")[0].strip()
    return (request.client.host if request.client else "unknown") or "unknown"


def _rate_limited(ip: str) -> bool:
    now = time.time()
    if len(_hits) > MAX_CLIENTS:  # keep the bucket table from growing forever
        for stale_ip in [k for k, v in _hits.items() if not v or now - v[-1] > RATE_WINDOW][:1000]:
            _hits.pop(stale_ip, None)
    bucket = _hits.setdefault(ip, deque())
    while bucket and now - bucket[0] > RATE_WINDOW:
        bucket.popleft()
    if len(bucket) >= RATE_LIMIT:
        return True
    bucket.append(now)
    return False


def _cached(address: str) -> Optional[Report]:
    entry = _reports.get(address)
    if entry and time.time() - entry[0] < REPORT_TTL:
        return entry[1]
    return None


def _store(report: Report) -> None:
    if len(_reports) >= MAX_CACHED:
        oldest = min(_reports, key=lambda k: _reports[k][0])
        _reports.pop(oldest, None)
    _reports[report.address] = (time.time(), report)


async def _run(address: str, chains: Optional[list[str]], include_native: bool) -> Report:
    report = _cached(address)
    if report is not None:
        return report
    try:
        report = await asyncio.wait_for(
            audit_address(
                address,
                chains_filter=chains,
                include_native=include_native,
                cache_path=os.path.join(HERE, "cache", "rpc.sqlite"),
            ),
            timeout=SCAN_TIMEOUT,
        )
    except asyncio.TimeoutError as exc:
        raise HTTPException(status_code=504, detail="انتهى وقت الفحص، حاول مرة أخرى") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _store(report)
    _served["audits"] += 1
    _served["findings"] += len(report.findings)
    return report


@app.get("/", response_class=HTMLResponse)
async def index() -> HTMLResponse:
    page = os.path.join(STATIC_DIR, "index.html")
    if os.path.exists(page):
        return HTMLResponse(open(page, encoding="utf-8").read())
    return HTMLResponse(render_error("landing page missing", 500), status_code=500)


@app.exception_handler(RequestValidationError)
async def _validation_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    return JSONResponse(
        status_code=400,
        content={
            "detail": "العنوان غير صحيح: أدخل 0x متبوعة بـ 40 خانة ست عشرية",
            "errors": exc.errors(),
        },
    )


@app.post("/api/audit")
async def api_audit(payload: AuditRequest, request: Request) -> JSONResponse:
    if _rate_limited(_client_ip(request)):
        raise HTTPException(status_code=429, detail="عدد الفحوصات كبير، انتظر قليلاً")
    was_cached = _cached(payload.address) is not None
    report = await _run(payload.address, payload.chains, payload.include_native)
    return JSONResponse({**report.to_dict(), "cached": was_cached})


@app.get("/report/{address}", response_class=HTMLResponse)
async def report_page(address: str) -> HTMLResponse:
    try:
        report = await _run(address.strip().lower(), None, True)
    except HTTPException as exc:
        return HTMLResponse(
            render_error(str(exc.detail), exc.status_code), status_code=exc.status_code
        )
    return HTMLResponse(render_report(report))


@app.get("/kit/digixdao", response_class=HTMLResponse)
async def kit_index(address: str = "") -> Response:
    """Landing form; a query-string address redirects to the canonical path."""
    value = address.strip()
    if value:
        return RedirectResponse(f"/kit/digixdao/{value.lower()}", status_code=307)
    return HTMLResponse(render_kit_form())


@app.get("/kit/digixdao/{address}", response_class=HTMLResponse)
async def kit_page(address: str, request: Request) -> HTMLResponse:
    if _rate_limited(_client_ip(request)):
        return HTMLResponse(
            render_kit_error("عدد الفحوصات كبير، انتظر قليلاً", 429), status_code=429
        )
    try:
        kit = await asyncio.wait_for(load_kit(address.strip().lower()), timeout=20)
    except asyncio.TimeoutError:
        return HTMLResponse(
            render_kit_error("انتهى وقت القراءة من الشبكة، حاول مرة أخرى", 504), status_code=504
        )
    except ValueError as exc:
        return HTMLResponse(render_kit_error(str(exc), 400), status_code=400)
    return HTMLResponse(render_kit(kit))


@app.get("/api/kit/digixdao/{address}")
async def kit_api(address: str, request: Request) -> JSONResponse:
    if _rate_limited(_client_ip(request)):
        raise HTTPException(status_code=429, detail="عدد الفحوصات كبير، انتظر قليلاً")
    try:
        kit = await asyncio.wait_for(load_kit(address.strip().lower()), timeout=20)
    except asyncio.TimeoutError as exc:
        raise HTTPException(status_code=504, detail="انتهى وقت القراءة من الشبكة") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return JSONResponse(kit.to_dict())


@app.get("/health")
async def health() -> dict:
    return {
        "status": "ok",
        "cached_reports": len(_reports),
        "audits_served": _served["audits"],
        "eth_price_available": _reports and bool(next(iter(_reports.values()))[1].eth_usd) or False,
    }


@app.get("/api/stats")
async def stats() -> dict:
    return {
        "audits_served": _served["audits"],
        "findings_found": _served["findings"],
        "cached_reports": len(_reports),
        "contracts_in_db": CONTRACTS_IN_DB,
        "chains": 20,
    }


@app.get("/favicon.ico")
async def favicon() -> FileResponse:
    path = os.path.join(STATIC_DIR, "favicon.svg")
    if os.path.exists(path):
        return FileResponse(path, media_type="image/svg+xml")
    raise HTTPException(status_code=404)
