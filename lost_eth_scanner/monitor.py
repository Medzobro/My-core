#!/usr/bin/env python3
"""
LOST ETH MONITOR
================
Continuously watches a set of addresses and alerts when:
  - A new stuck balance appears (someone deposits to one of your addresses)
  - A balance changes (someone withdrew or moved)
  - A new contract receives a withdraw event from your address

Useful for:
  - Long-term passive monitoring
  - Detecting if anyone is interacting with your old wallets
  - Catching forgotten airdrops or refunds

Usage:
    python3 monitor.py 0xAddr1 [0xAddr2 ...]
    python3 monitor.py --interval 300 --webhook https://discord.com/api/webhooks/... 0xAddr
"""
import argparse
import asyncio
import json
import os
import sys
import time
from typing import Optional

import aiohttp
import certifi
import ssl

# Reuse scanner_v2 components
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from scanner_v2 import (
    load_config, MultiRPC, scan_address, C
)

STATE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'monitor_state.json')


def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE) as f:
            return json.load(f)
    return {}


def save_state(state):
    with open(STATE_FILE, 'w') as f:
        json.dump(state, f, indent=2, default=str)


def diff_balances(prev, curr):
    """Compare two scan results, return list of changes."""
    changes = []
    prev_b = {}
    curr_b = {}
    for ca, info in (prev.get('findings_per_contract') or {}).items():
        for b in info['balances']:
            key = (ca, b['token'])
            prev_b[key] = b
    for ca, info in (curr.get('findings_per_contract') or {}).items():
        for b in info['balances']:
            key = (ca, b['token'])
            curr_b[key] = b

    for k in set(prev_b) | set(curr_b):
        p = prev_b.get(k)
        c = curr_b.get(k)
        if p is None:
            changes.append({'type': 'NEW', 'contract': k[0], 'token': k[1], 'amount': c['amount'], 'symbol': c.get('symbol','?')})
        elif c is None:
            changes.append({'type': 'WITHDRAWN', 'contract': k[0], 'token': k[1], 'amount': p['amount'], 'symbol': p.get('symbol','?')})
        elif str(p['amount_raw']) != str(c['amount_raw']):
            changes.append({
                'type': 'CHANGED', 'contract': k[0], 'token': k[1],
                'before': p['amount'], 'after': c['amount'], 'symbol': c.get('symbol','?')
            })
    return changes


async def post_webhook(session, url, message):
    if not url:
        return
    try:
        # Discord-style webhook
        if 'discord.com' in url:
            await session.post(url, json={'content': message}, timeout=aiohttp.ClientTimeout(total=10))
        else:
            # generic
            await session.post(url, json={'message': message}, timeout=aiohttp.ClientTimeout(total=10))
    except Exception:
        pass


async def monitor(addresses, interval, webhook, chains_filter, concurrency):
    chains, contracts, tokens_db = load_config()
    state = load_state()

    print(f'{C.BOLD}LOST ETH MONITOR{C.RESET}')
    print(f'  Addresses: {len(addresses)}')
    print(f'  Interval:  {interval}s')
    print(f'  Webhook:   {webhook or "(none)"}')
    print(f'  State:     {STATE_FILE}')

    sem = asyncio.Semaphore(concurrency)
    ssl_ctx = ssl.create_default_context(cafile=certifi.where())
    iteration = 0

    while True:
        iteration += 1
        print(f'\n{C.MAGENTA}>>> Cycle #{iteration} at {time.strftime("%Y-%m-%d %H:%M:%S")}{C.RESET}')

        async with aiohttp.ClientSession(connector=aiohttp.TCPConnector(limit=concurrency, ssl=ssl_ctx)) as session:
            rpc = MultiRPC(chains, session, sem)

            for addr in addresses:
                addr = addr.lower()
                if not (addr.startswith('0x') and len(addr) == 42):
                    continue
                curr = await scan_address(rpc, contracts, addr, tokens_db, chains_filter, include_native=False)
                prev = state.get(addr, {})

                changes = diff_balances(prev, curr)
                if changes:
                    print(f'\n  {C.YELLOW}{C.BOLD}CHANGES DETECTED for {addr}:{C.RESET}')
                    msgs = []
                    for ch in changes:
                        if ch['type'] == 'NEW':
                            msg = f'NEW balance: {ch["amount"]:.6f} {ch["symbol"]} in {ch["contract"][:10]}...'
                        elif ch['type'] == 'WITHDRAWN':
                            msg = f'WITHDRAWN: {ch["amount"]:.6f} {ch["symbol"]} from {ch["contract"][:10]}...'
                        else:
                            msg = f'CHANGED: {ch["before"]:.6f} -> {ch["after"]:.6f} {ch["symbol"]} in {ch["contract"][:10]}...'
                        print(f'    {C.YELLOW}{msg}{C.RESET}')
                        msgs.append(msg)
                    if webhook:
                        await post_webhook(session, webhook,
                            f'**Lost ETH Monitor** - changes for `{addr}`:\n' + '\n'.join(f'- {m}' for m in msgs))
                else:
                    print(f'  {C.GRAY}{addr}: no changes ({curr["total_findings"]} balances){C.RESET}')

                state[addr] = curr

        save_state(state)
        print(f'\n{C.GRAY}State saved. Next scan in {interval}s. (Ctrl+C to stop){C.RESET}')
        await asyncio.sleep(interval)


def main():
    p = argparse.ArgumentParser(description='Lost ETH Monitor - continuous watch for forgotten balances')
    p.add_argument('addresses', nargs='+')
    p.add_argument('--interval', type=int, default=300, help='Scan interval in seconds (default 300)')
    p.add_argument('--webhook', default=None, help='Discord/generic webhook for alerts')
    p.add_argument('--chains', default='', help='Comma-separated chains (default: all)')
    p.add_argument('--concurrency', type=int, default=80)
    args = p.parse_args()

    chains_filter = set(c.strip() for c in args.chains.split(',') if c.strip()) if args.chains else None

    try:
        asyncio.run(monitor(args.addresses, args.interval, args.webhook, chains_filter, args.concurrency))
    except KeyboardInterrupt:
        print(f'\n{C.YELLOW}Monitor stopped.{C.RESET}')


if __name__ == '__main__':
    main()
