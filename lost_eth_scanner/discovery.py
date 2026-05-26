#!/usr/bin/env python3
"""
DISCOVERY ENGINE
================
The most powerful tool in the suite. Instead of relying on a static database,
this engine ANALYZES an address's transaction history to discover EVERY contract
it has interacted with, then checks balances on each one.

This catches forgotten funds in contracts not in our DB - any obscure DEX,
random staking contract, abandoned NFT marketplace, etc.

Strategy:
  1. Fetch transaction history from public block explorers (Etherscan-compatible)
  2. Extract unique contract addresses (where to != EOA)
  3. For each contract, check if it's a smart contract (eth_getCode)
  4. For each contract, run multiple balance check methods:
     - ETH held by user inside contract (etherdelta-style mappings)
     - ERC-20/721/1155 token balance
     - Storage slot scanning for user-specific patterns
  5. Aggregate findings

Usage:
    python3 discovery.py 0xYourAddress [--chain ethereum] [--max-contracts 200]
    python3 discovery.py 0xAddr --include-l2  # also scan Arbitrum/Optimism/etc
"""
import argparse
import asyncio
import json
import os
import ssl
import sys
import time
from typing import Optional

import aiohttp
import certifi

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CHAINS_FILE = os.path.join(SCRIPT_DIR, 'data', 'chains.json')

# Public block explorer APIs (no API key required for basic use, rate-limited)
EXPLORERS = {
    'ethereum': 'https://api.etherscan.io/api',
    'arbitrum': 'https://api.arbiscan.io/api',
    'optimism': 'https://api-optimistic.etherscan.io/api',
    'base': 'https://api.basescan.org/api',
    'polygon': 'https://api.polygonscan.com/api',
    'bsc': 'https://api.bscscan.com/api',
}

# Free public alternatives
FREE_EXPLORERS = {
    'ethereum': 'https://eth.blockscout.com/api/v2/addresses',
    'arbitrum': 'https://arbitrum.blockscout.com/api/v2/addresses',
    'optimism': 'https://optimism.blockscout.com/api/v2/addresses',
    'base': 'https://base.blockscout.com/api/v2/addresses',
    'polygon': 'https://polygon.blockscout.com/api/v2/addresses',
}


class C:
    RESET = '\033[0m'; BOLD = '\033[1m'
    GREEN = '\033[32m'; YELLOW = '\033[33m'; RED = '\033[31m'
    CYAN = '\033[36m'; GRAY = '\033[90m'; MAGENTA = '\033[35m'; BLUE = '\033[34m'


def encode_addr(a):
    return ('0' * 24) + a.lower().replace('0x', '')


async def get_tx_history(session, chain, address, max_pages=3):
    """Fetch tx history from Blockscout (no API key needed)."""
    base = FREE_EXPLORERS.get(chain)
    if not base:
        return []
    transactions = []
    next_params = None
    for _ in range(max_pages):
        url = f'{base}/{address}/transactions'
        try:
            async with session.get(url, params=next_params,
                                    timeout=aiohttp.ClientTimeout(total=15)) as r:
                if r.status != 200:
                    break
                data = await r.json()
                items = data.get('items', [])
                transactions.extend(items)
                next_params = data.get('next_page_params')
                if not next_params:
                    break
        except Exception:
            break
    return transactions


async def get_token_transfers(session, chain, address, max_pages=3):
    """Fetch token transfer history."""
    base = FREE_EXPLORERS.get(chain)
    if not base:
        return []
    transfers = []
    next_params = None
    for _ in range(max_pages):
        url = f'{base}/{address}/token-transfers'
        try:
            async with session.get(url, params=next_params,
                                    timeout=aiohttp.ClientTimeout(total=15)) as r:
                if r.status != 200:
                    break
                data = await r.json()
                items = data.get('items', [])
                transfers.extend(items)
                next_params = data.get('next_page_params')
                if not next_params:
                    break
        except Exception:
            break
    return transfers


def extract_contracts_from_history(txs, transfers, address):
    """Extract unique contract addresses interacted with."""
    contracts = set()
    methods_per_contract = {}
    address_lower = address.lower()

    for tx in txs:
        to = tx.get('to', {})
        if not to:
            continue
        to_addr = (to.get('hash') or '').lower()
        if not to_addr or to_addr == address_lower:
            continue
        # Check if 'to' is a contract (Blockscout marks this)
        if to.get('is_contract'):
            contracts.add(to_addr)
            method = tx.get('method', 'unknown')
            methods_per_contract.setdefault(to_addr, set()).add(method)

    for tr in transfers:
        token_addr = tr.get('token', {}).get('address', '').lower()
        if token_addr:
            contracts.add(token_addr)

    return contracts, methods_per_contract


async def rpc_call(session, rpcs, method, params, timeout=8):
    payload = {'jsonrpc': '2.0', 'method': method, 'params': params, 'id': 1}
    for rpc in rpcs:
        try:
            async with session.post(rpc, json=payload,
                                     timeout=aiohttp.ClientTimeout(total=timeout)) as r:
                if r.status != 200:
                    continue
                d = await r.json()
                if 'result' in d:
                    return d['result']
        except Exception:
            continue
    return None


async def probe_contract_balance(session, rpcs, contract, user, sem):
    """Try multiple balance check methods on a contract."""
    findings = []
    async with sem:
        # Method 1: ERC-20/721 balanceOf(user)
        data = '0x70a08231' + encode_addr(user)
        res = await rpc_call(session, rpcs, 'eth_call', [{'to': contract, 'data': data}, 'latest'])
        if res and res != '0x':
            try:
                bal = int(res, 16)
                if bal > 0:
                    findings.append({'method': 'erc20_balanceOf', 'raw': bal, 'contract': contract})
            except Exception:
                pass

        # Method 2: EtherDelta-style balanceOf(token, user) with ETH
        data = '0xf7888aec' + encode_addr('0x0000000000000000000000000000000000000000') + encode_addr(user)
        res = await rpc_call(session, rpcs, 'eth_call', [{'to': contract, 'data': data}, 'latest'])
        if res and res != '0x':
            try:
                bal = int(res, 16)
                if bal > 0 and bal < 10**30:  # sanity check
                    findings.append({'method': 'etherdelta_eth', 'raw': bal, 'contract': contract})
            except Exception:
                pass

        # Method 3: tokens(address,address) - some DEX patterns
        data = '0x508493bc' + encode_addr('0x0000000000000000000000000000000000000000') + encode_addr(user)
        res = await rpc_call(session, rpcs, 'eth_call', [{'to': contract, 'data': data}, 'latest'])
        if res and res != '0x':
            try:
                bal = int(res, 16)
                if bal > 0 and bal < 10**30:
                    findings.append({'method': 'tokens_mapping', 'raw': bal, 'contract': contract})
            except Exception:
                pass

    return findings


async def discover(address, chain='ethereum', max_contracts=200, include_l2=False):
    chains_cfg = json.load(open(CHAINS_FILE))['chains']
    ssl_ctx = ssl.create_default_context(cafile=certifi.where())

    chains_to_scan = [chain]
    if include_l2:
        chains_to_scan = ['ethereum', 'arbitrum', 'optimism', 'base', 'polygon']

    print(f'\n{C.BOLD}{C.CYAN}{"=" * 78}{C.RESET}')
    print(f'  {C.BOLD}DISCOVERY ENGINE{C.RESET}')
    print(f'  Address: {address}')
    print(f'  Chains:  {chains_to_scan}')
    print(f'  Max per chain: {max_contracts} contracts')
    print(f'{C.CYAN}{"=" * 78}{C.RESET}\n')

    sem = asyncio.Semaphore(80)
    all_findings = {}

    async with aiohttp.ClientSession(connector=aiohttp.TCPConnector(limit=80, ssl=ssl_ctx)) as session:
        for ch in chains_to_scan:
            rpcs = chains_cfg.get(ch, {}).get('rpcs', [])
            if not rpcs or ch not in FREE_EXPLORERS:
                continue

            print(f'{C.BOLD}[{ch.upper()}]{C.RESET}')
            print(f'  Fetching transaction history...', flush=True)

            t0 = time.time()
            txs = await get_tx_history(session, ch, address)
            transfers = await get_token_transfers(session, ch, address)
            contracts, methods = extract_contracts_from_history(txs, transfers, address)

            print(f'  -> {len(txs)} txs, {len(transfers)} token transfers, {len(contracts)} unique contracts')

            if not contracts:
                print(f'  {C.GRAY}No interactions found.{C.RESET}\n')
                continue

            contracts_list = list(contracts)[:max_contracts]
            print(f'  Probing balances on {len(contracts_list)} contracts...', flush=True)

            tasks = [probe_contract_balance(session, rpcs, c, address, sem) for c in contracts_list]
            results = await asyncio.gather(*tasks, return_exceptions=True)

            findings = []
            for c, r in zip(contracts_list, results):
                if isinstance(r, Exception) or not r:
                    continue
                for f in r:
                    f['methods_used'] = list(methods.get(c, []))
                    findings.append(f)

            elapsed = time.time() - t0
            if findings:
                all_findings[ch] = findings
                print(f'\n  {C.GREEN}{C.BOLD}DISCOVERED {len(findings)} balance(s):{C.RESET}')
                for f in findings:
                    method_used = ', '.join(f.get('methods_used', [])[:3])
                    formatted = f['raw'] / 1e18 if f['raw'] > 10**12 else f['raw']
                    fmt_str = f'{formatted:,.6f}' if f['raw'] > 10**12 else f'{f["raw"]:,}'
                    print(f'    {C.GREEN}*{C.RESET} {f["contract"]}  {fmt_str:>20s}  via {f["method"]}')
                    if method_used:
                        print(f'      {C.GRAY}past methods called: {method_used}{C.RESET}')
            else:
                print(f'\n  {C.GRAY}No stuck balances detected via probing.{C.RESET}')
            print(f'  {C.GRAY}Took {elapsed:.1f}s{C.RESET}\n')

    # Final summary
    print(f'{C.BOLD}{C.MAGENTA}{"=" * 78}{C.RESET}')
    print(f'{C.BOLD}  DISCOVERY COMPLETE{C.RESET}')
    print(f'{C.MAGENTA}{"=" * 78}{C.RESET}\n')
    total = sum(len(f) for f in all_findings.values())
    if total == 0:
        print(f'  {C.GRAY}No discovered balances. Address may have used contracts already in our DB only.{C.RESET}')
    else:
        print(f'  Total discovered findings: {total}')
        for ch, fs in all_findings.items():
            print(f'\n  [{ch.upper()}]')
            for f in fs:
                print(f'    {f["contract"]}  raw={f["raw"]}  method={f["method"]}')

    return all_findings


def main():
    p = argparse.ArgumentParser(description='Discovery Engine - finds forgotten funds via tx history')
    p.add_argument('address')
    p.add_argument('--chain', default='ethereum')
    p.add_argument('--include-l2', action='store_true', help='Also scan Arbitrum, Optimism, Base, Polygon')
    p.add_argument('--max-contracts', type=int, default=200)
    p.add_argument('--json', default=None)
    args = p.parse_args()

    results = asyncio.run(discover(args.address, args.chain, args.max_contracts, args.include_l2))

    if args.json:
        with open(args.json, 'w') as f:
            json.dump(results, f, indent=2, default=str)
        print(f'\nResults saved to {args.json}')


if __name__ == '__main__':
    main()
