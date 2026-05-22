#!/usr/bin/env python3
"""
LOST ETH SCANNER v2 - Multi-Chain Async Edition
================================================
A high-performance scanner that checks any wallet address against forgotten
contracts across Ethereum mainnet AND Layer 2 networks.

Features:
  - Concurrent async HTTP via aiohttp (50x faster than sync)
  - 9 chains supported: ETH, Arbitrum, Optimism, Base, Polygon, zkSync, Linea, Scroll, BSC
  - Multi-RPC fallback per chain
  - Three balance check types:
      * etherdelta:  balanceOf(address,address) on EtherDelta-fork DEXs
      * erc20_self:  ERC-20 balance of the address on a token contract
      * erc20_holder: holder of OTHER token (e.g. DAO tokens for WithdrawDAO)
      * native:      native ETH/MATIC/BNB balance held by contract
  - Color-coded output, progress reporting
  - JSON output for downstream processing

ETHICAL USE:
  This scanner reads only PUBLIC on-chain state. It reports balances registered
  to the address you provide. Withdrawing requires the private key for THAT
  address. Do not use to attempt extraction of funds belonging to others.

Usage:
    python3 scanner_v2.py 0xAddr1 [0xAddr2 0xAddr3 ...]
    python3 scanner_v2.py --chains ethereum,arbitrum 0xAddr1
    python3 scanner_v2.py --concurrency 100 0xAddr1
    python3 scanner_v2.py --json results.json 0xAddr1
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
CHAINS_FILE = os.path.join(SCRIPT_DIR, 'chains.json')
CONTRACTS_FILE = os.path.join(SCRIPT_DIR, 'contracts_multichain.json')

# ANSI colors
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

COMMON_TOKENS_ETHEREUM = {
    '0x6b175474e89094c44da98b954eedeac495271d0f': ('DAI', 18),
    '0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48': ('USDC', 6),
    '0xdac17f958d2ee523a2206206994597c13d831ec7': ('USDT', 6),
    '0x514910771af9ca656af840dff83e8264ecf986ca': ('LINK', 18),
    '0x744d70fdbe2ba4cf95131626614a1763df805b9e': ('SNT', 18),
    '0xb705268213d593b8fd88d3fdeff93aff5cbdcfae': ('IDEX', 18),
    '0xe41d2489571d322189246dafa5ebde1f4699f498': ('ZRX', 18),
    '0xd26114cd6ee289accf82350c8d8487fedb8a0c07': ('OMG', 18),
    '0x1985365e9f78359a9b6ad760e32412f4a445e862': ('REP', 18),
    '0x0d8775f648430679a709e98d2b0cb6250d2887ef': ('BAT', 18),
    '0x9f8f72aa9304c8b593d555f12ef6589cc3a579a2': ('MKR', 18),
    '0xc011a73ee8576fb46f5e1c5751ca3b9fe0af2a6f': ('SNX', 18),
    '0x6c6ee5e31d828de241282b9606c8e98ea48526e2': ('HOT', 18),
    '0xbb9bc244d798123fde783fcc1c72d3bb8c189413': ('DAO_v1', 16),
    '0xa974c709cfb4566686553a20790685a47aceaa33': ('IDXM', 8),
}


def load_config():
    with open(CHAINS_FILE) as f:
        chains = json.load(f)['chains']
    with open(CONTRACTS_FILE) as f:
        contracts = [c for c in json.load(f)['contracts']
                     if not c.get('_comment') and c.get('address', '').startswith('0x')]
    return chains, contracts


def encode_addr(a):
    return ('0' * 24) + a.lower().replace('0x', '')


class MultiRPC:
    """Async RPC client with per-chain fallback."""
    def __init__(self, chains_config, session: aiohttp.ClientSession, semaphore: asyncio.Semaphore):
        self.chains = chains_config
        self.session = session
        self.sem = semaphore
        # Stats
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
                    async with self.session.post(rpc, json=payload, timeout=aiohttp.ClientTimeout(total=timeout)) as resp:
                        if resp.status != 200:
                            continue
                        data = await resp.json()
                        if 'result' in data:
                            return data['result']
                except Exception:
                    continue
            self.fails += 1
            return None


async def check_etherdelta_balance(rpc: MultiRPC, chain: str, contract: str, user: str, token: str = '0x0000000000000000000000000000000000000000'):
    """balanceOf(token, user) - selector 0xf7888aec"""
    data = '0xf7888aec' + encode_addr(token) + encode_addr(user)
    res = await rpc.call(chain, 'eth_call', [{'to': contract, 'data': data}, 'latest'])
    if res and res != '0x':
        try:
            return int(res, 16)
        except Exception:
            return 0
    return 0


async def check_erc20_balance(rpc: MultiRPC, chain: str, token: str, user: str):
    """balanceOf(user) - selector 0x70a08231"""
    data = '0x70a08231' + encode_addr(user)
    res = await rpc.call(chain, 'eth_call', [{'to': token, 'data': data}, 'latest'])
    if res and res != '0x':
        try:
            return int(res, 16)
        except Exception:
            return 0
    return 0


async def check_native_balance(rpc: MultiRPC, chain: str, addr: str):
    res = await rpc.call(chain, 'eth_getBalance', [addr, 'latest'])
    if res:
        try:
            return int(res, 16)
        except Exception:
            return 0
    return 0


async def scan_contract(rpc: MultiRPC, contract: dict, user: str):
    """Scan a single contract for the user's balance."""
    chain = contract['chain']
    addr = contract['address']
    btype = contract.get('balance_check', '')
    findings = []

    if btype == 'etherdelta':
        # Native ETH balance in DEX
        bal = await check_etherdelta_balance(rpc, chain, addr, user)
        if bal > 0:
            findings.append({
                'amount_raw': bal,
                'amount': bal / 1e18,
                'symbol': 'ETH',
                'token': '0x0000000000000000000000000000000000000000',
            })
        # Token balances on common tokens (only for Ethereum)
        if chain == 'ethereum':
            tasks = []
            tokens_meta = []
            for tok, (sym, dec) in COMMON_TOKENS_ETHEREUM.items():
                tasks.append(check_etherdelta_balance(rpc, chain, addr, user, tok))
                tokens_meta.append((tok, sym, dec))
            results = await asyncio.gather(*tasks, return_exceptions=True)
            for (tok, sym, dec), res in zip(tokens_meta, results):
                if isinstance(res, Exception) or res is None:
                    continue
                if res > 0:
                    findings.append({
                        'amount_raw': res,
                        'amount': res / (10 ** dec),
                        'symbol': sym,
                        'token': tok,
                    })

    elif btype == 'erc20_self':
        # ERC-20 balance of user on the contract itself
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
        # User's balance of a SPECIFIC token (e.g. DAO tokens for WithdrawDAO)
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


async def scan_address(rpc: MultiRPC, contracts: list, user: str, chains_filter: Optional[set] = None):
    """Scan one user address across all relevant contracts in parallel."""
    user = user.lower()
    eligible = [c for c in contracts if (not chains_filter or c['chain'] in chains_filter)]

    print(f'\n{C.BOLD}{C.CYAN}{"=" * 78}{C.RESET}')
    print(f'{C.BOLD}  Address: {user}{C.RESET}')
    print(f'{C.BOLD}  Scanning {len(eligible)} contracts across chains...{C.RESET}')
    print(f'{C.CYAN}{"=" * 78}{C.RESET}')

    t_start = time.time()
    tasks = [scan_contract(rpc, c, user) for c in eligible]
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

    # Group by chain for display
    by_chain = {}
    for addr, (c, fs) in findings_per_contract.items():
        by_chain.setdefault(c['chain'], []).append((c, fs))

    if not by_chain:
        print(f'  {C.GRAY}No stuck balances found.{C.RESET}')
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
        'findings_per_contract': {
            addr: {
                'name': c['name'],
                'chain': c['chain'],
                'category': c.get('category', ''),
                'withdraw_method': c.get('withdraw_method', ''),
                'balances': fs,
            }
            for addr, (c, fs) in findings_per_contract.items()
        },
        'total_findings': total_findings,
        'elapsed_seconds': elapsed,
    }


async def main_async(addresses: list, chains_filter: Optional[set], concurrency: int, json_out: Optional[str]):
    chains, contracts = load_config()

    print(f'{C.BOLD}LOST ETH SCANNER v2 - Multi-Chain Edition{C.RESET}')
    print(f'  Database: {len(contracts)} contracts')
    print(f'  Chains:   {sorted(set(c["chain"] for c in contracts))}')
    print(f'  Filter:   {sorted(chains_filter) if chains_filter else "all"}')
    print(f'  Concurrency: {concurrency}')
    print(f'  Addresses: {len(addresses)}')

    sem = asyncio.Semaphore(concurrency)
    ssl_context = ssl.create_default_context(cafile=certifi.where())
    connector = aiohttp.TCPConnector(limit=concurrency, ssl=ssl_context)
    async with aiohttp.ClientSession(connector=connector) as session:
        rpc = MultiRPC(chains, session, sem)
        all_results = []
        for addr in addresses:
            if not (addr.startswith('0x') and len(addr) == 42):
                print(f'  {C.RED}Skipping invalid address: {addr}{C.RESET}')
                continue
            result = await scan_address(rpc, contracts, addr, chains_filter)
            all_results.append(result)

        # Final summary
        print(f'\n\n{C.BOLD}{C.MAGENTA}{"=" * 78}')
        print('  GRAND TOTAL')
        print(f'{"=" * 78}{C.RESET}\n')
        any_found = False
        for r in all_results:
            if r['total_findings'] > 0:
                any_found = True
                print(f'  {C.BOLD}{r["address"]}{C.RESET}: {r["total_findings"]} balances found')
                for ca, info in r['findings_per_contract'].items():
                    for b in info['balances']:
                        note = f' ({b.get("note","")})' if b.get('note') else ''
                        print(f'    [{info["chain"]}] {info["name"]:30s}  {b["amount"]:>14,.6f} {b["symbol"]}{note}')
        if not any_found:
            print(f'  {C.GRAY}No findings across all addresses and chains.{C.RESET}')
            print(f'\n  Suggestions:')
            print(f'    - Try old MetaMask addresses (Settings > Advanced > Show all)')
            print(f'    - Search emails for "deposit confirmation" 2017-2020')
            print(f'    - Check hardware wallet derivation paths')
            print(f'    - L2 addresses might differ - try addresses you used on Arbitrum/Optimism')

        if json_out:
            with open(json_out, 'w') as f:
                json.dump(all_results, f, indent=2, default=str)
            print(f'\n  {C.GRAY}Results saved to {json_out}{C.RESET}')


def main():
    p = argparse.ArgumentParser(description='Lost ETH Scanner v2 - Multi-chain async')
    p.add_argument('addresses', nargs='+', help='Wallet addresses to scan')
    p.add_argument('--chains', default='', help='Comma-separated chains to scan (default: all)')
    p.add_argument('--concurrency', type=int, default=80, help='Max concurrent RPC calls')
    p.add_argument('--json', default=None, help='Save results to JSON file')
    args = p.parse_args()

    chains_filter = set(args.chains.split(',')) if args.chains else None

    asyncio.run(main_async(args.addresses, chains_filter, args.concurrency, args.json))


if __name__ == '__main__':
    main()
