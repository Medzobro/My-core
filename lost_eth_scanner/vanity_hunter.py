#!/usr/bin/env python3
"""
VANITY ADDRESS HUNTER
======================
Novel research: find contracts whose admin/owner addresses bear hallmarks of
vanity-generation (esp. Profanity-tool style). Profanity used a 32-bit seed and
its keys were cracked in 2022 - leading to $3.3M+ drained from Wintermute and
others. Many old contracts may STILL have Profanity-generated admin keys.

What we look for, per contract:
  1. owner() / admin() / governance() / authority() resolutions
  2. Storage slot 0 (often the owner mapping)
  3. Vanity score per owner: leading zeros, repeated chars, dictionary words
  4. Owner activity: last tx / balance - if dormant, likely lost-key candidate
  5. Contract balance + token holdings

Output: ranked target list by (USD value x vanity score).
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


def _hex_no_prefix(a: str) -> str:
    return a.lower().replace('0x', '')


def vanity_score(addr: str) -> dict:
    h = _hex_no_prefix(addr)
    if len(h) != 40 or not all(c in '0123456789abcdef' for c in h):
        return {'score': 0, 'reasons': ['invalid']}

    score = 0
    reasons = []

    leading_zeros = 0
    for c in h:
        if c == '0':
            leading_zeros += 1
        else:
            break
    if leading_zeros >= 4:
        score += leading_zeros * 5
        reasons.append(f'leading_zeros={leading_zeros}')

    trailing_zeros = 0
    for c in reversed(h):
        if c == '0':
            trailing_zeros += 1
        else:
            break
    if trailing_zeros >= 4:
        score += trailing_zeros * 3
        reasons.append(f'trailing_zeros={trailing_zeros}')

    longest_run = 1
    cur = 1
    for i in range(1, len(h)):
        if h[i] == h[i - 1]:
            cur += 1
            longest_run = max(longest_run, cur)
        else:
            cur = 1
    if longest_run >= 5:
        score += longest_run * 4
        reasons.append(f'repeated_run={longest_run}')

    DICTIONARY = [
        'dead', 'beef', 'cafe', 'babe', 'face', 'feed', 'fade', 'fee5',
        'c0ff', 'd0ff', 'b0ff', 'b00b', 'baddad',
        'bad', 'b1d', 'a55', 'a11', 'b33f',
        'add', 'ace', 'aaa', 'fff',
        '0123', '4321', 'bee', 'b00',
        '1111', '2222', '3333', '4444', '5555',
    ]
    word_hits = []
    h_low = h.lower()
    for w in DICTIONARY:
        if w.lower() in h_low:
            word_hits.append(w)
    if word_hits:
        score += len(word_hits) * 6
        reasons.append(f'dict_words={word_hits[:5]}')

    if leading_zeros >= 6 or trailing_zeros >= 6:
        score += 30
        reasons.append('profanity_likely')

    BURN_ADDRESSES = {
        '0000000000000000000000000000000000000000': 'zero_addr',
        'dead000000000000000042069420694206942069': 'eip1559_burn',
        '0000000000000000000000000000000000000001': 'precompile',
        '000000000000000000000000000000000000dead': 'common_burn',
    }
    if h in BURN_ADDRESSES:
        score = -1
        reasons = [f'BURN: {BURN_ADDRESSES[h]}']

    return {'score': score, 'reasons': reasons,
            'leading_zeros': leading_zeros,
            'trailing_zeros': trailing_zeros,
            'longest_run': longest_run}


def likely_profanity(profile: dict) -> bool:
    return (profile.get('leading_zeros', 0) >= 5
            or profile.get('trailing_zeros', 0) >= 5
            or profile.get('longest_run', 0) >= 6)


async def rpc_call(session, sem, rpcs, method, params, timeout=8.0):
    payload = {'jsonrpc': '2.0', 'method': method, 'params': params, 'id': 1}
    async with sem:
        for url in rpcs:
            try:
                async with session.post(url, json=payload,
                                        timeout=aiohttp.ClientTimeout(total=timeout)) as r:
                    if r.status != 200:
                        continue
                    d = await r.json()
                    if 'result' in d:
                        return d['result']
            except Exception:
                continue
    return None


async def get_owners(session, sem, rpcs, contract_addr) -> dict:
    OWNER_SELECTORS = {
        '8da5cb5b': 'owner()',
        '893d20e8': 'getOwner()',
        'f851a440': 'admin()',
        '5aa6e675': 'governance()',
        'bf7e214f': 'authority()',
        'b918161c': 'controller()',
    }
    findings = {}
    for sel, name in OWNER_SELECTORS.items():
        r = await rpc_call(session, sem, rpcs, 'eth_call',
                           [{'to': contract_addr, 'data': '0x' + sel}, 'latest'])
        if r and r != '0x' and len(r) >= 66:
            cand = '0x' + r[-40:]
            if int(cand, 16) > 1:
                findings[name] = cand

    for slot in (0, 1, 2):
        r = await rpc_call(session, sem, rpcs, 'eth_getStorageAt',
                           [contract_addr, hex(slot), 'latest'])
        if r and r != '0x' and len(r) >= 66:
            v = '0x' + r[-40:]
            if int(v, 16) > 1 and v not in findings.values():
                findings[f'storage_slot_{slot}'] = v

    return findings


async def get_activity(session, sem, rpcs, addr) -> dict:
    bal = await rpc_call(session, sem, rpcs, 'eth_getBalance', [addr, 'latest'])
    nonce = await rpc_call(session, sem, rpcs, 'eth_getTransactionCount',
                           [addr, 'latest'])
    code = await rpc_call(session, sem, rpcs, 'eth_getCode', [addr, 'latest'])
    return {
        'balance_eth': int(bal, 16) / 1e18 if bal else 0,
        'nonce': int(nonce, 16) if nonce else 0,
        'is_contract': bool(code and code != '0x'),
    }


async def hunt_one(session, sem, rpcs, contract):
    addr = contract['address']
    bal_h = await rpc_call(session, sem, rpcs, 'eth_getBalance', [addr, 'latest'])
    bal = int(bal_h, 16) if bal_h else 0
    if bal == 0:
        return None

    owners = await get_owners(session, sem, rpcs, addr)
    if not owners:
        return None

    candidates = []
    seen = set()
    for source, owner_addr in owners.items():
        if owner_addr.lower() in seen:
            continue
        seen.add(owner_addr.lower())
        profile = vanity_score(owner_addr)
        if profile['score'] <= 0:
            continue
        activity = await get_activity(session, sem, rpcs, owner_addr)
        candidates.append({
            'owner_source': source,
            'owner_address': owner_addr,
            'vanity_score': profile['score'],
            'vanity_reasons': profile['reasons'],
            'profanity_likely': likely_profanity(profile),
            'owner_balance_eth': activity['balance_eth'],
            'owner_nonce': activity['nonce'],
            'owner_is_contract': activity['is_contract'],
        })

    if not candidates:
        return None

    return {
        'chain': contract['chain'],
        'name': contract.get('name', '?'),
        'address': addr,
        'category': contract.get('category', ''),
        'contract_balance_eth': bal / 1e18,
        'owners': candidates,
    }


async def main():
    chains = json.load(open(os.path.join(SCRIPT_DIR, 'data', 'chains.json')))['chains']
    contracts = json.load(open(os.path.join(SCRIPT_DIR, 'data', 'contracts_multichain.json')))['contracts']
    contracts = [c for c in contracts
                 if not c.get('_comment') and c.get('address', '').startswith('0x')]

    print(f'[*] Vanity Address Hunter: scanning {len(contracts)} contracts')
    print(f'[*] Looking for vanity-generated owner/admin keys')

    sem = asyncio.Semaphore(15)
    ssl_ctx = ssl.create_default_context(cafile=certifi.where())
    connector = aiohttp.TCPConnector(limit=30, ssl=ssl_ctx)

    t0 = time.time()
    candidates = []

    async with aiohttp.ClientSession(connector=connector) as session:
        by_chain = defaultdict(list)
        for c in contracts:
            by_chain[c['chain']].append(c)

        for chain, ch_list in by_chain.items():
            cfg = chains.get(chain)
            if not cfg:
                continue
            rpcs = cfg['rpcs']
            tasks = [hunt_one(session, sem, rpcs, c) for c in ch_list]
            for done in asyncio.as_completed(tasks):
                r = await done
                if r:
                    candidates.append(r)
                    top = max(o['vanity_score'] for o in r['owners'])
                    flag = ' PROFANITY?' if any(o['profanity_likely'] for o in r['owners']) else ''
                    print(f"  [{r['chain']:10s}] score={top:>4}  bal={r['contract_balance_eth']:>10,.4f}  "
                          f"{r['name'][:35]:35s}{flag}")

    elapsed = time.time() - t0

    def composite(r):
        return r['contract_balance_eth'] * max(o['vanity_score'] for o in r['owners'])

    candidates.sort(key=composite, reverse=True)

    print('\n' + '=' * 100)
    print('  VANITY HUNT REPORT')
    print('=' * 100)
    print(f'  Scanned in {elapsed:.1f}s')
    print(f'  Found {len(candidates)} contracts with vanity-pattern owners\n')

    for i, r in enumerate(candidates[:30]):
        print(f"\n[{i+1}] {r['chain'].upper()}  {r['name']}")
        print(f"    contract:         {r['address']}")
        print(f"    contract balance: {r['contract_balance_eth']:,.4f} native")
        print(f"    category:         {r['category']}")
        for o in r['owners']:
            prof = ' [PROFANITY?]' if o['profanity_likely'] else ''
            print(f"      [{o['owner_source']:15s}] {o['owner_address']}{prof}")
            print(f"        score={o['vanity_score']}  reasons={o['vanity_reasons']}")
            print(f"        owner_balance={o['owner_balance_eth']:,.4f} ETH  nonce={o['owner_nonce']}")

    out = os.path.join(SCRIPT_DIR, 'results', 'vanity_hunt_results.json')
    os.makedirs(os.path.dirname(out), exist_ok=True)
    json.dump(candidates, open(out, 'w'), indent=2, default=str)
    print(f'\n[*] Saved: {out}')


if __name__ == '__main__':
    asyncio.run(main())
