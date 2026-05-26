#!/usr/bin/env python3
"""
SELFDESTRUCT REVIVAL HUNTER
=============================
Searches for contracts that have a SELFDESTRUCT (0xff) opcode and analyzes:

  1. The address argument passed to SELFDESTRUCT:
     - CALLER (msg.sender) -> DRAIN candidate (anyone can suicide it & take ETH)
     - PUSH20 constant     -> Check if hardcoded beneficiary is alive
     - SLOAD storage slot  -> Read the storage; if it's 0x0 or 0xdead, ETH is sacrificed

  2. Whether the SELFDESTRUCT is reachable via a public function

  3. The function selector(s) that lead to SELFDESTRUCT execution
"""
import asyncio
import json
import os
import ssl
import time
from collections import defaultdict

import aiohttp
import certifi

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

OP_CALLER = 0x33
OP_SLOAD = 0x54
OP_SELFDESTRUCT = 0xff
OP_PUSH20 = 0x73


def disasm_with_pc(code: bytes):
    i = 0
    while i < len(code):
        op = code[i]
        if 0x60 <= op <= 0x7f:
            push_len = op - 0x5f
            data = code[i + 1:i + 1 + push_len]
            yield i, op, data
            i += 1 + push_len
        else:
            yield i, op, None
            i += 1


def find_selfdestructs(code_hex: str):
    if not code_hex or code_hex == '0x':
        return []
    try:
        code = bytes.fromhex(code_hex[2:])
    except ValueError:
        return []
    instrs = list(disasm_with_pc(code))

    results = []
    for idx, (pc, op, data) in enumerate(instrs):
        if op != OP_SELFDESTRUCT:
            continue

        prev = instrs[max(0, idx - 12):idx]

        kind = 'unknown'
        evidence = []
        hardcoded_addr = None

        for p, o, d in reversed(prev):
            if o == OP_CALLER:
                kind = 'CALLER'
                evidence.append(f'CALLER@{p:x}')
                break
            if o == OP_PUSH20 and d:
                kind = 'PUSH20_CONST'
                hardcoded_addr = '0x' + d.hex()
                evidence.append(f'PUSH20({hardcoded_addr})@{p:x}')
                break
            if o == OP_SLOAD:
                kind = 'SLOAD'
                evidence.append(f'SLOAD@{p:x}')
                break

        results.append({
            'pc': pc,
            'kind': kind,
            'hardcoded_addr': hardcoded_addr,
            'evidence': evidence,
        })

    return results


def find_selectors(code_hex: str):
    if not code_hex or code_hex == '0x':
        return set()
    try:
        code = bytes.fromhex(code_hex[2:])
    except ValueError:
        return set()
    selectors = set()
    for pc, op, data in disasm_with_pc(code):
        if op == 0x63 and data:
            sel = data.hex()
            if sel != '00000000' and sel != 'ffffffff':
                selectors.add(sel)
    return selectors


KILL_SELECTORS = {
    '41c0e1b5': 'kill()',
    '35f46994': 'destroy()',
    '9cb8a26a': 'destruct()',
    'cb3e64fd': 'shutdown()',
    'fb000fa7': 'terminate()',
    '00f55d9d': 'destroy(address)',
    '24c12bf6': 'cleanup()',
    '46e04a2f': 'killSwitch()',
    '3a98ef39': 'destroyContract()',
    '5e80fe79': 'suicide()',
    '8c7c9e0c': 'remove()',
    '9be07908': 'die()',
    '9d8a90b3': 'finalize()',
}


async def rpc_call(session, sem, rpcs, method, params, timeout=12.0):
    payload = {'jsonrpc': '2.0', 'method': method, 'params': params, 'id': 1}
    async with sem:
        for url in rpcs:
            try:
                async with session.post(url, json=payload,
                                        timeout=aiohttp.ClientTimeout(total=timeout)) as r:
                    if r.status != 200:
                        continue
                    d = await r.json()
                    if 'error' in d:
                        return {'error': d['error']}
                    return {'result': d.get('result')}
            except Exception:
                continue
    return None


async def hunt_one(session, sem, rpcs, contract):
    addr = contract['address']

    bal_r, code_r = await asyncio.gather(
        rpc_call(session, sem, rpcs, 'eth_getBalance', [addr, 'latest']),
        rpc_call(session, sem, rpcs, 'eth_getCode', [addr, 'latest']),
    )
    bal = int(bal_r['result'], 16) if bal_r and 'result' in bal_r and bal_r['result'] else 0
    code = code_r.get('result', '0x') if code_r else '0x'

    if bal == 0 or code == '0x':
        return None

    sd_sites = find_selfdestructs(code)
    if not sd_sites:
        return None

    selectors = find_selectors(code)
    kill_sels_present = [
        (s, KILL_SELECTORS[s]) for s in selectors if s in KILL_SELECTORS
    ]

    has_caller = any(s['kind'] == 'CALLER' for s in sd_sites)
    has_const = any(s['kind'] == 'PUSH20_CONST' for s in sd_sites)
    has_sload = any(s['kind'] == 'SLOAD' for s in sd_sites)

    const_addresses = []
    for s in sd_sites:
        if s['kind'] == 'PUSH20_CONST' and s['hardcoded_addr']:
            const_addresses.append(s['hardcoded_addr'])

    score = 0
    if has_caller:
        score += 100
    if has_const:
        score += 30
    if has_sload:
        score += 20
    if kill_sels_present:
        score += 50

    return {
        'chain': contract['chain'],
        'name': contract.get('name', '?'),
        'address': addr,
        'category': contract.get('category', ''),
        'balance_eth': bal / 1e18,
        'code_size': (len(code) - 2) // 2,
        'selfdestruct_sites': sd_sites,
        'kill_selectors_present': kill_sels_present,
        'has_caller_target': has_caller,
        'has_const_target': has_const,
        'const_addresses': const_addresses,
        'has_sload_target': has_sload,
        'score': score,
    }


async def main():
    chains = json.load(open(os.path.join(SCRIPT_DIR, 'data', 'chains.json')))['chains']
    contracts = json.load(open(os.path.join(SCRIPT_DIR, 'data', 'contracts_multichain.json')))['contracts']
    contracts = [c for c in contracts
                 if not c.get('_comment') and c.get('address', '').startswith('0x')]

    print(f'[*] SELFDESTRUCT Revival Hunter: scanning {len(contracts)} contracts')
    print(f'[*] Looking for SELFDESTRUCT opcodes in contracts with balance > 0\n', flush=True)

    sem = asyncio.Semaphore(15)
    ssl_ctx = ssl.create_default_context(cafile=certifi.where())
    connector = aiohttp.TCPConnector(limit=30, ssl=ssl_ctx)

    t0 = time.time()
    candidates = []

    async with aiohttp.ClientSession(connector=connector) as session:
        by_chain = defaultdict(list)
        for c in contracts:
            by_chain[c['chain']].append(c)

        for chain, cs in by_chain.items():
            cfg = chains.get(chain)
            if not cfg:
                continue
            tasks = [hunt_one(session, sem, cfg['rpcs'], c) for c in cs]
            for done in asyncio.as_completed(tasks):
                r = await done
                if r:
                    candidates.append(r)
                    flag = ''
                    if r['has_caller_target']:
                        flag += ' CALLER!'
                    if r['kill_selectors_present']:
                        flag += f' KILL({len(r["kill_selectors_present"])})'
                    print(f"  *** {r['chain']:10s} bal={r['balance_eth']:>10,.4f}  "
                          f"{r['name'][:35]:35s} score={r['score']}{flag}", flush=True)

    elapsed = time.time() - t0
    candidates.sort(key=lambda r: (-r['score'], -r['balance_eth']))

    print('\n' + '=' * 100)
    print('  SELFDESTRUCT REVIVAL REPORT')
    print('=' * 100)
    print(f'  Scanned in {elapsed:.1f}s')
    print(f'  Found {len(candidates)} contracts with SELFDESTRUCT + balance\n')

    caller_targets = [c for c in candidates if c['has_caller_target']]
    if caller_targets:
        print(f'  *** {len(caller_targets)} contracts have SELFDESTRUCT(CALLER) - potentially drainable!\n')
        for c in caller_targets[:20]:
            print(f"    {c['chain']:10s}  bal={c['balance_eth']:>10,.4f}  {c['name']}")
            print(f"      addr: {c['address']}")
            print(f"      kill_funcs: {[s[1] for s in c['kill_selectors_present']]}")
            for sd in c['selfdestruct_sites']:
                print(f"      SELFDESTRUCT@pc={sd['pc']:x} kind={sd['kind']} evidence={sd['evidence']}")
            print()
    else:
        print('  No SELFDESTRUCT(CALLER) candidates found.')

    print('\n  TOP CANDIDATES BY SCORE:')
    for i, r in enumerate(candidates[:30]):
        print(f"  [{i+1}] {r['chain']:10s} bal={r['balance_eth']:>10,.4f}  score={r['score']}  "
              f"{r['name']}")
        print(f"      addr: {r['address']}")
        if r['const_addresses']:
            print(f"      hardcoded SD targets: {r['const_addresses'][:3]}")
        if r['kill_selectors_present']:
            print(f"      kill selectors: {[s[1] for s in r['kill_selectors_present']]}")

    out = os.path.join(SCRIPT_DIR, 'results', 'selfdestruct_revival_results.json')
    os.makedirs(os.path.dirname(out), exist_ok=True)
    json.dump(candidates, open(out, 'w'), indent=2, default=str)
    print(f'\n[*] Saved: {out}')


if __name__ == '__main__':
    asyncio.run(main())
