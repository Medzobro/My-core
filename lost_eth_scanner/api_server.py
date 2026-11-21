#!/usr/bin/env python3
"""
LOST ETH API SERVER
===================
A FastAPI server exposing the scanner functionality as REST endpoints.
Use this to power web UIs, mobile apps, or integrate into other tools.

Endpoints:
  GET  /              - Status and stats
  GET  /chains        - List supported chains
  GET  /contracts     - List all contracts in DB
  POST /scan          - Scan a single or multiple addresses
  POST /airdrops      - Check airdrop eligibility/holdings
  POST /nfts          - Check NFT holdings
  POST /withdraw_data - Generate raw tx data for withdraw
  GET  /health        - Health check

Usage:
    pip install fastapi uvicorn
    python3 api_server.py
    # OR
    uvicorn api_server:app --host 0.0.0.0 --port 8000
"""
import asyncio
import os
import ssl
import sys
from typing import List, Optional

import aiohttp
import certifi
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from scanner_v2 import load_config, MultiRPC, scan_address


app = FastAPI(
    title="Lost ETH Scanner API",
    description="Multi-chain forgotten Ethereum funds discovery service",
    version="2.0.0",
)

# CORS for web UI consumption
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============== MODELS ==============
class ScanRequest(BaseModel):
    addresses: List[str]
    chains: Optional[List[str]] = None
    include_native: bool = False


class WithdrawDataRequest(BaseModel):
    contract: str
    token: str = "0x0000000000000000000000000000000000000000"
    amount_wei: str  # string to handle big ints
    method_type: str = "etherdelta"  # or "withdraw_dao", "free", "withdraw_simple"


# ============== STATE ==============
chains_cfg = None
contracts_db = None
tokens_db = None
ssl_ctx = None


@app.on_event("startup")
async def startup():
    global chains_cfg, contracts_db, tokens_db, ssl_ctx
    chains_cfg, contracts_db, tokens_db = load_config()
    ssl_ctx = ssl.create_default_context(cafile=certifi.where())


# ============== ENDPOINTS ==============
@app.get("/")
async def root():
    return {
        "service": "Lost ETH Scanner API",
        "version": "2.0.0",
        "stats": {
            "chains": len(chains_cfg),
            "contracts": len(contracts_db),
            "tokens": sum(len(t) for t in tokens_db.values()),
        },
        "endpoints": ["/chains", "/contracts", "/scan", "/airdrops", "/nfts", "/withdraw_data", "/health"],
    }


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/chains")
async def list_chains():
    return {
        "chains": [
            {
                "id": k,
                "chain_id": v.get("chain_id"),
                "name": v.get("name"),
                "explorer": v.get("explorer"),
                "native_token": v.get("native_token"),
                "rpc_count": len(v.get("rpcs", [])),
            }
            for k, v in chains_cfg.items()
        ]
    }


@app.get("/contracts")
async def list_contracts(chain: Optional[str] = None, category: Optional[str] = None):
    items = contracts_db
    if chain:
        items = [c for c in items if c.get("chain") == chain]
    if category:
        items = [c for c in items if c.get("category") == category]
    return {"count": len(items), "contracts": items}


@app.post("/scan")
async def scan(req: ScanRequest):
    if len(req.addresses) > 50:
        raise HTTPException(400, "Max 50 addresses per request")
    for a in req.addresses:
        if not (a.startswith("0x") and len(a) == 42):
            raise HTTPException(400, f"Invalid address: {a}")

    sem = asyncio.Semaphore(80)
    chains_filter = set(req.chains) if req.chains else None

    async with aiohttp.ClientSession(
        connector=aiohttp.TCPConnector(limit=80, ssl=ssl_ctx)
    ) as session:
        rpc = MultiRPC(chains_cfg, session, sem)
        results = []
        for addr in req.addresses:
            r = await scan_address(rpc, contracts_db, addr, tokens_db, chains_filter, req.include_native)
            results.append(r)
        return {"results": results, "rpc_calls": rpc.calls, "rpc_fails": rpc.fails}


@app.post("/withdraw_data")
async def withdraw_data(req: WithdrawDataRequest):
    """Generate raw call data for various withdraw methods."""
    def encode_addr(a):
        return a.lower().replace("0x", "").rjust(64, "0")
    def encode_uint(n):
        return f"{int(n):064x}"

    method = req.method_type
    if method == "etherdelta":
        # withdraw(address,uint256) selector 0xf3fef3a3
        data = "0xf3fef3a3" + encode_addr(req.token) + encode_uint(req.amount_wei)
    elif method == "withdraw_simple":
        # withdraw(uint256) selector 0x2e1a7d4d
        data = "0x2e1a7d4d" + encode_uint(req.amount_wei)
    elif method == "withdraw_dao":
        # WithdrawDAO.withdraw() selector 0x3ccfd60b
        data = "0x3ccfd60b"
    elif method == "free":
        # GST2/CHI free(uint256) selector 0xb1e349a3
        data = "0xb1e349a3" + encode_uint(req.amount_wei)
    else:
        raise HTTPException(400, f"Unknown method type: {method}")

    return {
        "to": req.contract,
        "value": "0",
        "data": data,
        "gas_estimate": 100000,
    }


@app.post("/airdrops")
async def airdrops(req: ScanRequest):
    """Check airdrop token holdings."""
    from airdrop_checker import AIRDROPS

    results = []
    async with aiohttp.ClientSession(
        connector=aiohttp.TCPConnector(limit=50, ssl=ssl_ctx)
    ) as session:
        for address in req.addresses:
            address = address.lower()
            if not (address.startswith("0x") and len(address) == 42):
                continue
            holdings = []
            tasks = []
            valid_ads = []
            for ad in AIRDROPS:
                if ad.get("chain") == "solana" or not ad.get("token"):
                    continue
                rpcs = chains_cfg.get(ad["chain"], {}).get("rpcs", [])
                if not rpcs:
                    continue
                from airdrop_checker import check_token_balance
                tasks.append(check_token_balance(session, rpcs, ad["token"], address))
                valid_ads.append(ad)

            balances = await asyncio.gather(*tasks, return_exceptions=True)
            for ad, bal in zip(valid_ads, balances):
                if isinstance(bal, Exception) or bal is None or bal == 0:
                    continue
                holdings.append({
                    "name": ad["name"],
                    "symbol": ad["token_symbol"],
                    "amount": bal / (10 ** ad["token_decimals"]),
                    "amount_raw": str(bal),
                    "chain": ad["chain"],
                    "note": ad.get("note", ""),
                })
            results.append({"address": address, "holdings": holdings})

    return {"results": results}


@app.post("/nfts")
async def nfts(req: ScanRequest):
    """Check NFT holdings."""
    from nft_scanner import NFT_COLLECTIONS, check_erc721_balance

    eth_rpcs = chains_cfg["ethereum"]["rpcs"]
    results = []
    async with aiohttp.ClientSession(
        connector=aiohttp.TCPConnector(limit=80, ssl=ssl_ctx)
    ) as session:
        for address in req.addresses:
            address = address.lower()
            if not (address.startswith("0x") and len(address) == 42):
                continue
            tasks = [check_erc721_balance(session, eth_rpcs, c["address"], address) for c in NFT_COLLECTIONS]
            counts = await asyncio.gather(*tasks, return_exceptions=True)
            holdings = []
            for col, count in zip(NFT_COLLECTIONS, counts):
                if isinstance(count, Exception) or count is None or count == 0:
                    continue
                holdings.append({
                    "name": col["name"],
                    "address": col["address"],
                    "count": count,
                })
            results.append({"address": address, "holdings": holdings})

    return {"results": results}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
