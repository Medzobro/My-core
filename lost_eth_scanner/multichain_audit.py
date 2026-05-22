#!/usr/bin/env python3
"""
MULTICHAIN FORENSIC AUDIT
==========================
Async sweep of every contract in contracts_multichain.json across all chains.

For each contract:
  1. Native balance (ETH/MATIC/BNB)
  2. Bytecode size + selectors + opcodes
  3. Detection of permissionless patterns (withdraw, claim, sweep, rescue)
  4. Owner check (owner(), getOwner(), admin())

Final report:
  - Sorted by USD-ish weight (balance) per chain
  - Flags contracts that have BALANCE > 0.01 native AND a permissionless selector
    (these are the only candidates worth a closer look)
"""
import asyncio, json, os, ssl, time
import aiohttp, certifi

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CHAINS_FILE = os.path.join(SCRIPT_DIR, 'chains.json')
CONTRACTS_FILE = os.path.join(SCRIPT_DIR, 'contracts_multichain.json')

PERMISSIONLESS_SELECTORS = {
    '3ccfd60b': 'withdraw()',
    '4e71d92d': 'claim()',
    '4ae53a7c': 'sweep()',
    'c30436e9': 'rescue()',
    '6b9f96ea': 'flush()',
    'd0a9405c': 'forward()',
    '78cd1d56': 'collect()',
    'e9fad8ee': 'exit()',
    '853828b6': 'withdrawAll()',
    '00f714ce': 'withdraw(uint256,address)',
    '2e1a7d4d': 'withdraw(uint256)',
}

OWNER_SELECTORS = {
    '8da5cb5b': 'owner()',
    '893d20e8': 'getOwner()',
    'f851a440': 'admin()',
}


def encode_addr(a):
    return ('0' * 24) + a.lower().replace('0x', '')


def extract_selectors(code_hex):
    if not code_hex or code_hex == '0x':
        return set()
    raw = code_hex[2:].lower()
    sels = set()
    i = 0
    while i < len(raw) - 10:
        if raw[i:i + 2] == '63':  # PUSH4
            s = raw[i + 2:i + 10]
            if s != '00000000' and s != 'ffffffff':
                sels.add(s)
            i += 10
        else:
            i += 2
    return sels


async def rpc_call(session, sem, rpcs, method, params, timeout=8.0):
    payload = {'jsonrpc': '2.0', 'method': method, 'params': params, 'id': 1}
    async with sem:
        for url in rpcs:
            try:
                async with session.post(url, json=payload,
                                        timeout=aiohttp.ClientTimeout(total=timeout)) as resp:
                    if resp.status != 200:
                        continue
                    data = await resp.json()
                    if 'result' in data:
                        return data['result']
            except Exception:
                continue
    return None


async def audit_contract(session, sem, chain_cfg, contract):
    addr = contract['address']
    rpcs = chain_cfg['rpcs']

    bal_hex, code = await asyncio.gather(
        rpc_call(session, sem, rpcs, 'eth_getBalance', [addr, 'latest']),
        rpc_call(session, sem, rpcs, 'eth_getCode', [addr, 'latest']),
    )

    bal_wei = int(bal_hex, 16) if bal_hex else 0
    code_size = (len(code) - 2) // 2 if code and code != '0x' else 0
    is_contract = code is not None and code != '0x'

    selectors = extract_selectors(code) if is_contract else set()
    perm_hits = [v for k, v in PERMISSIONLESS_SELECTORS.items() if k in selectors]

    # Owner check (only if the contract has owner-pattern selector)
    owner = None
    for sel, name in OWNER_SELECTORS.items():
        if sel in selectors:
            r = await rpc_call(session, sem, rpcs, 'eth_call',
                               [{'to': addr, 'data': '0x' + sel}, 'latest'])
            if r and r != '0x' and len(r) >= 66:
                cand = '0x' + r[-40:]
                if int(cand, 16) > 0:
                    owner = {'address': cand, 'method': name}
                    break

    return {
        'chain': contract['chain'],
        'name': contract.get('name', '?'),
        'address': addr,
        'category': contract.get('category', ''),
        'balance_native': bal_wei / 1e18,
        'is_contract': is_contract,
        'code_size': code_size,
        'permissionless': perm_hits,
        'owner': owner,
        'selectors_count': len(selectors),
    }


async def main():
    with open(CHAINS_FILE) as f:
        chains = json.load(f)['chains']
    with open(CONTRACTS_FILE) as f:
        contracts = [c for c in json.load(f)['contracts']
                     if not c.get('_comment') and c.get('address', '').startswith('0x')]

    print(f'[*] Auditing {len(contracts)} contracts across {len(chains)} chains...')
    t0 = time.time()
    sem = asyncio.Semaphore(40)
    ssl_ctx = ssl.create_default_context(cafile=certifi.where())
    connector = aiohttp.TCPConnector(limit=60, ssl=ssl_ctx)

    async with aiohttp.ClientSession(connector=connector) as session:
        tasks = []
        for c in contracts:
            cfg = chains.get(c['chain'])
            if not cfg:
                continue
            tasks.append(audit_contract(session, sem, cfg, c))
        results = await asyncio.gather(*tasks, return_exceptions=True)

    results = [r for r in results if isinstance(r, dict)]
    elapsed = time.time() - t0
    print(f'[*] Done in {elapsed:.1f}s\n')

    # Sort by balance desc, group by chain
    results.sort(key=lambda r: (-r['balance_native'], r['chain']))

    print('=' * 90)
    print('  ALL RESULTS - SORTED BY NATIVE BALANCE')
    print('=' * 90)
    total_per_chain = {}
    for r in results:
        ch = r['chain']
        bal = r['balance_native']
        total_per_chain[ch] = total_per_chain.get(ch, 0) + bal
        flag = ''
        if r['permissionless']:
            flag = '  [!! PERMISSIONLESS:' + ','.join(r['permissionless']) + ']'
        elif r['owner']:
            flag = f"  [owner={r['owner']['address'][:10]}...]"
        elif not r['is_contract']:
            flag = '  [NOT A CONTRACT]'
        print(f"  {ch:10s} {bal:>14,.4f}  {r['name'][:35]:35s} {r['address']}{flag}")

    print('\n' + '=' * 90)
    print('  TOTAL BY CHAIN')
    print('=' * 90)
    grand_total_eth = 0
    for ch, tot in sorted(total_per_chain.items(), key=lambda x: -x[1]):
        grand_total_eth += tot if ch in ('ethereum', 'arbitrum', 'optimism', 'base', 'zksync', 'linea', 'scroll') else 0
        print(f'  {ch:12s} {tot:>14,.4f}')

    # ⚠️ Recoverability candidates: balance > 0 AND permissionless pattern
    print('\n' + '=' * 90)
    print('  PERMISSIONLESS CANDIDATES (balance > 0.01 + open withdraw selector)')
    print('=' * 90)
    candidates = [r for r in results
                  if r['balance_native'] > 0.01 and r['permissionless']]
    if not candidates:
        print('  (none)  -  no contract with balance has an obviously open withdraw fn')
    else:
        for c in candidates:
            print(f"  [{c['chain']}] {c['name']:35s}  {c['balance_native']:>12,.4f}")
            print(f"      addr: {c['address']}")
            print(f"      open: {c['permissionless']}")
            print(f"      cat:  {c['category']}")
            print()

    out = os.path.join(SCRIPT_DIR, 'multichain_audit_results.json')
    with open(out, 'w') as f:
        json.dump(results, f, indent=2, default=str)
    print(f'\n[*] Full JSON saved to: {out}')


if __name__ == '__main__':
    asyncio.run(main())
