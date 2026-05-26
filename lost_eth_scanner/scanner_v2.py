#!/usr/bin/env python3
"""
LOST ETH SCANNER v2 - Multi-Chain Async Edition
================================================
A high-performance scanner that checks any wallet address against forgotten
contracts across Ethereum mainnet AND Layer 2 networks.

Features:
  - Concurrent async HTTP via aiohttp (50x faster than sync)
  - 9 chains: ETH, Arbitrum, Optimism, Base, Polygon, zkSync, Linea, Scroll, BSC
  - Multi-RPC fallback per chain
  - Token database per chain (~100+ tokens scanned per address)
  - 4 balance check types:
      * etherdelta:   balanceOf(address,address) on EtherDelta-fork DEXs
      * erc20_self:   ERC-20 balance on the contract itself (cTokens, GST2)
      * erc20_holder: holder of OTHER token (e.g. DAO tokens for WithdrawDAO)
      * native:       native ETH/MATIC/BNB held by user (for L2 dust)
  - Color-coded output with progress
  - JSON output for downstream tools
  - Watch mode (continuously polls for new findings)

ETHICAL USE:
  Reads PUBLIC on-chain state for the address you provide.
  Withdrawing requires the private key for THAT address.

Usage:
    python3 scanner_v2.py 0xAddr1 [0xAddr2 ...]
    python3 scanner_v2.py --chains ethereum,arbitrum 0xAddr1
    python3 scanner_v2.py --concurrency 100 0xAddr
    python3 scanner_v2.py --json results.json 0xAddr
    python3 scanner_v2.py --watch --interval 60 0xAddr
    python3 scanner_v2.py --include-native 0xAddr      # also report L1/L2 wallet balances
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
CONTRACTS_FILE = os.path.join(SCRIPT_DIR, 'data', 'contracts_multichain.json')
TOKENS_FILE = os.path.join(SCRIPT_DIR, 'data', 'tokens_multichain.json')


class C:
    RESET = '\033[0m'
    BOLD = '\033[1m'
    GREEN = '\033[32m'
    YELLOW = '\033[33m'
    RED = '\033[31m'
    BLUE = '\033[34m'
    CYAN = '\033[36m'
    GRAY = '\033[90m'
    MAGENTA = '\033[35m'


def load_config():
    with open(CHAINS_FILE) as f:
        chains = json.load(f)['chains']
    with open(CONTRACTS_FILE) as f:
        contracts = [c for c in json.load(f)['contracts']
                     if not c.get('_comment') and c.get('address', '').startswith('0x')]
    tokens = {}
    if os.path.exists(TOKENS_FILE):
        with open(TOKENS_FILE) as f:
            raw = json.load(f)
            for chain, toks in raw.items():
                if chain.startswith('_'):
                    continue
                # filter out dummy entries
                tokens[chain] = {addr.split('_')[0]: meta for addr, meta in toks.items()
                                 if addr.startswith('0x') and len(addr.split('_')[0]) == 42}
    return chains, contracts, tokens


def encode_addr(a):
    return ('0' * 24) + a.lower().replace('0x', '')


class MultiRPC:
    def __init__(self, chains_config, session: aiohttp.ClientSession, semaphore: asyncio.Semaphore):
        self.chains = chains_config
        self.session = session
        self.sem = semaphore
        self.calls = 0
        self.fails = 0

    async def call(self, chain: str, method: str, params: list, timeout: float = 8.0):
        async with self.sem:
            self.calls += 1
            chain_cfg = self.chains.get(chain)
            if not chain_cfg:
                self.fails += 1
                return None
            payload = {'jsonrpc': '2.0', 'method': method, 'params': params, 'id': 1}
            for rpc in chain_cfg['rpcs']:
                try:
                    async with self.session.post(rpc, json=payload,
                                                 timeout=aiohttp.ClientTimeout(total=timeout)) as resp:
                        if resp.status != 200:
                            continue
                        data = await resp.json()
                        if 'result' in data:
                            return data['result']
                except Exception:
                    continue
            self.fails += 1
            return None


async def check_etherdelta_balance(rpc, chain, contract, user, token='0x0000000000000000000000000000000000000000'):
    """balanceOf(token, user) selector 0xf7888aec"""
    data = '0xf7888aec' + encode_addr(token) + encode_addr(user)
    res = await rpc.call(chain, 'eth_call', [{'to': contract, 'data': data}, 'latest'])
    if res and res != '0x':
        try:
            return int(res, 16)
        except Exception:
            return 0
    return 0


async def check_erc20_balance(rpc, chain, token, user):
    """balanceOf(user) selector 0x70a08231"""
    data = '0x70a08231' + encode_addr(user)
    res = await rpc.call(chain, 'eth_call', [{'to': token, 'data': data}, 'latest'])
    if res and res != '0x':
        try:
            return int(res, 16)
        except Exception:
            return 0
    return 0


async def check_native_balance(rpc, chain, user):
    res = await rpc.call(chain, 'eth_getBalance', [user, 'latest'])
    if res:
        try:
            return int(res, 16)
        except Exception:
            return 0
    return 0


async def scan_contract(rpc, contract, user, tokens_db):
    """Scan one contract for the user's balance. Returns list of findings."""
    chain = contract['chain']
    addr = contract['address']
    btype = contract.get('balance_check', '')
    findings = []

    if btype == 'etherdelta':
        # Native (ETH) balance in DEX
        bal = await check_etherdelta_balance(rpc, chain, addr, user)
        if bal > 0:
            findings.append({
                'amount_raw': bal,
                'amount': bal / 1e18,
                'symbol': 'ETH',
                'token': '0x0000000000000000000000000000000000000000',
            })
        # Token balances - all known tokens for this chain
        chain_tokens = tokens_db.get(chain, {})
        if chain_tokens:
            tasks = [check_etherdelta_balance(rpc, chain, addr, user, tok) for tok in chain_tokens]
            metas = list(chain_tokens.items())
            results = await asyncio.gather(*tasks, return_exceptions=True)
            for (tok, meta), res in zip(metas, results):
                if isinstance(res, Exception) or res is None or res == 0:
                    continue
                sym, dec = meta
                findings.append({
                    'amount_raw': res,
                    'amount': res / (10 ** dec),
                    'symbol': sym,
                    'token': tok,
                })

    elif btype == 'erc20_self':
        bal = await check_erc20_balance(rpc, chain, addr, user)
        if bal > 0:
            dec = contract.get('balance_check_token_decimals', 18)
            findings.append({
                'amount_raw': bal,
                'amount': bal / (10 ** dec),
                'symbol': contract.get('name', '')[:10],
                'token': addr,
            })

    elif btype == 'erc20_holder':
        token = contract.get('balance_check_token')
        if token:
            bal = await check_erc20_balance(rpc, chain, token, user)
            if bal > 0:
                dec = contract.get('balance_check_token_decimals', 18)
                findings.append({
                    'amount_raw': bal,
                    'amount': bal / (10 ** dec),
                    'symbol': contract.get('balance_check_token_name', 'TOKEN'),
                    'token': token,
                    'note': contract.get('rate_note', ''),
                })

    return findings


async def scan_address(rpc, contracts, user, tokens_db, chains_filter=None, include_native=False):
    """Scan one user address across all relevant contracts in parallel."""
    user = user.lower()
    eligible = [c for c in contracts if (not chains_filter or c['chain'] in chains_filter)]

    print(f'\n{C.BOLD}{C.CYAN}{"=" * 78}{C.RESET}')
    print(f'{C.BOLD}  Address: {user}{C.RESET}')
    print(f'{C.BOLD}  Scanning {len(eligible)} contracts + tokens across chains...{C.RESET}')
    print(f'{C.CYAN}{"=" * 78}{C.RESET}')

    t_start = time.time()

    # 1. Native balances per chain (optional)
    native_findings = {}
    if include_native:
        native_chains = chains_filter if chains_filter else list(rpc.chains.keys())
        native_tasks = [check_native_balance(rpc, ch, user) for ch in native_chains]
        native_results = await asyncio.gather(*native_tasks, return_exceptions=True)
        for ch, res in zip(native_chains, native_results):
            if isinstance(res, Exception) or res is None or res == 0:
                continue
            symbol = rpc.chains[ch].get('native_token', 'ETH')
            native_findings[ch] = {'amount': res / 1e18, 'symbol': symbol, 'amount_raw': res}

    # 2. Contract scans
    tasks = [scan_contract(rpc, c, user, tokens_db) for c in eligible]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    elapsed = time.time() - t_start

    findings_per_contract = {}
    total_findings = 0
    for c, r in zip(eligible, results):
        if isinstance(r, Exception):
            continue
        if r:
            findings_per_contract[c['address']] = (c, r)
            total_findings += len(r)

    # Display
    if native_findings:
        print(f'\n  {C.BOLD}[NATIVE WALLET BALANCES]{C.RESET}')
        for ch, info in native_findings.items():
            print(f'    {C.BLUE}{ch.upper():12s}{C.RESET}  {info["amount"]:>16,.6f} {info["symbol"]}')

    by_chain = {}
    for addr, (c, fs) in findings_per_contract.items():
        by_chain.setdefault(c['chain'], []).append((c, fs))

    if not by_chain:
        print(f'\n  {C.GRAY}No stuck balances found in scanned contracts.{C.RESET}')
    else:
        for chain, items in sorted(by_chain.items()):
            print(f'\n  {C.BOLD}[{chain.upper()}]{C.RESET}')
            for c, fs in items:
                print(f'    {C.GREEN}{C.BOLD}FOUND{C.RESET} in {c["name"]} ({c["address"][:10]}...)')
                for f in fs:
                    note = f' {C.GRAY}({f.get("note","")}){C.RESET}' if f.get('note') else ''
                    print(f'         {C.YELLOW}->{C.RESET} {f["amount"]:>16,.6f} {f["symbol"]}{note}')

    print(f'\n  {C.GRAY}Scan took {elapsed:.2f}s, {rpc.calls} RPC calls, {rpc.fails} fails{C.RESET}')

    return {
        'address': user,
        'native_findings': {ch: {**info, 'amount_raw': str(info['amount_raw'])} for ch, info in native_findings.items()},
        'findings_per_contract': {
            addr: {
                'name': c['name'],
                'chain': c['chain'],
                'category': c.get('category', ''),
                'withdraw_method': c.get('withdraw_method', ''),
                'balances': [{**b, 'amount_raw': str(b['amount_raw'])} for b in fs],
            }
            for addr, (c, fs) in findings_per_contract.items()
        },
        'total_findings': total_findings,
        'elapsed_seconds': elapsed,
    }


async def main_async(addresses, chains_filter, concurrency, json_out, watch, interval, include_native):
    chains, contracts, tokens_db = load_config()

    print(f'{C.BOLD}LOST ETH SCANNER v2 - Multi-Chain Edition{C.RESET}')
    print(f'  Database: {len(contracts)} contracts')
    token_total = sum(len(t) for t in tokens_db.values())
    print(f'  Tokens:   {token_total} across {len(tokens_db)} chains')
    print(f'  Chains:   {sorted(set(c["chain"] for c in contracts))}')
    print(f'  Filter:   {sorted(chains_filter) if chains_filter else "all"}')
    print(f'  Concurrency: {concurrency}')
    print(f'  Addresses: {len(addresses)}')
    if watch:
        print(f'  {C.YELLOW}Watch mode: refresh every {interval}s{C.RESET}')

    sem = asyncio.Semaphore(concurrency)
    ssl_ctx = ssl.create_default_context(cafile=certifi.where())
    connector = aiohttp.TCPConnector(limit=concurrency, ssl=ssl_ctx)

    async def run_once():
        async with aiohttp.ClientSession(connector=aiohttp.TCPConnector(limit=concurrency, ssl=ssl_ctx)) as session:
            rpc = MultiRPC(chains, session, sem)
            all_results = []
            for addr in addresses:
                if not (addr.startswith('0x') and len(addr) == 42):
                    print(f'  {C.RED}Skipping invalid address: {addr}{C.RESET}')
                    continue
                result = await scan_address(rpc, contracts, addr, tokens_db, chains_filter, include_native)
                all_results.append(result)

            print(f'\n\n{C.BOLD}{C.MAGENTA}{"=" * 78}')
            print('  GRAND TOTAL')
            print(f'{"=" * 78}{C.RESET}\n')
            any_found = False
            for r in all_results:
                if r['total_findings'] > 0 or r.get('native_findings'):
                    any_found = True
                    print(f'  {C.BOLD}{r["address"]}{C.RESET}')
                    if r.get('native_findings'):
                        for ch, info in r['native_findings'].items():
                            print(f'    [{ch:10s} wallet]                            {info["amount"]:>14,.6f} {info["symbol"]}')
                    for ca, info in r['findings_per_contract'].items():
                        for b in info['balances']:
                            note = f' ({b.get("note","")})' if b.get('note') else ''
                            print(f'    [{info["chain"]:10s}] {info["name"][:30]:30s}  {b["amount"]:>14,.6f} {b["symbol"]}{note}')
            if not any_found:
                print(f'  {C.GRAY}No findings across all addresses and chains.{C.RESET}')

            if json_out:
                with open(json_out, 'w') as f:
                    json.dump(all_results, f, indent=2, default=str)
                print(f'\n  {C.GRAY}Results saved to {json_out}{C.RESET}')

            return all_results

    if watch:
        iteration = 0
        while True:
            iteration += 1
            print(f'\n{C.MAGENTA}>>> Watch iteration #{iteration} at {time.strftime("%H:%M:%S")}{C.RESET}')
            await run_once()
            print(f'{C.GRAY}Sleeping {interval}s... (Ctrl+C to stop){C.RESET}')
            await asyncio.sleep(interval)
    else:
        await run_once()


def main():
    p = argparse.ArgumentParser(description='Lost ETH Scanner v2 - Multi-chain async')
    p.add_argument('addresses', nargs='+', help='Wallet addresses to scan')
    p.add_argument('--chains', default='', help='Comma-separated chains (default: all)')
    p.add_argument('--concurrency', type=int, default=80, help='Max concurrent RPC calls')
    p.add_argument('--json', default=None, help='Save results to JSON file')
    p.add_argument('--watch', action='store_true', help='Watch mode - keep scanning periodically')
    p.add_argument('--interval', type=int, default=60, help='Watch interval in seconds (default 60)')
    p.add_argument('--include-native', action='store_true', help='Also report direct wallet balances (L1/L2 dust)')
    args = p.parse_args()

    chains_filter = set(c.strip() for c in args.chains.split(',') if c.strip()) if args.chains else None

    try:
        asyncio.run(main_async(args.addresses, chains_filter, args.concurrency,
                                args.json, args.watch, args.interval, args.include_native))
    except KeyboardInterrupt:
        print(f'\n{C.YELLOW}Stopped.{C.RESET}')


if __name__ == '__main__':
    main()
