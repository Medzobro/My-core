#!/usr/bin/env python3
"""
COMPREHENSIVE CryptoPunks Recoverability Analysis
===================================================
The CryptoPunks V2 contract (0xb47e3cd8) holds ~3,332 ETH but pendingWithdrawals
sum is only ~2,247 ETH. The difference (~1,085 ETH) is locked in active bids
(punkBids[i]) - users who placed bids and never withdrew them.

This script:
  1. Scans ALL 10,000 punk bid slots, identifies bidders + amounts
  2. Combines with the 94 pendingWithdrawals from earlier scan
  3. Classifies each recoverable address: EOA / Contract
  4. Identifies dormant EOAs (likely lost-key)
"""
import asyncio
import json
import os
import ssl
import time

import aiohttp
import certifi

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

V2 = '0xb47e3cd837dDF8e4c57F05d70Ab865de6e193BBB'
V1 = '0x6BA6f2207e343923BA692e5Cae646Fb0F566DB8D'

PUNK_BIDS_SEL = '0xd9f5aed7'
PENDING_SEL = '0xf3f43703'


def encode_uint(n):
    return hex(n)[2:].rjust(64, '0')


def encode_addr(a):
    return ('0' * 24) + a.lower().replace('0x', '')


async def rpc_call(session, sem, rpcs, method, params, timeout=15.0):
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


async def get_punk_bid(session, sem, rpcs, contract, idx):
    cd = '0x' + PUNK_BIDS_SEL + encode_uint(idx)
    r = await rpc_call(session, sem, rpcs, 'eth_call',
                       [{'to': contract, 'data': cd}, 'latest'])
    if not r or 'result' not in r:
        return None
    res = r['result']
    if not res or res == '0x' or len(res) < 2 + 4 * 64:
        return None
    raw = res[2:]
    has_bid = int(raw[0:64], 16) == 1
    punk_index = int(raw[64:128], 16)
    bidder = '0x' + raw[128 + 24:192]
    value = int(raw[192:256], 16)
    return {'hasBid': has_bid, 'punkIndex': punk_index, 'bidder': bidder, 'value': value}


async def get_code_size(session, sem, rpcs, addr):
    r = await rpc_call(session, sem, rpcs, 'eth_getCode', [addr, 'latest'])
    if not r or 'result' not in r or not r['result']:
        return 0
    return (len(r['result']) - 2) // 2


async def get_balance(session, sem, rpcs, addr):
    r = await rpc_call(session, sem, rpcs, 'eth_getBalance', [addr, 'latest'])
    if not r or 'result' not in r or not r['result']:
        return 0
    return int(r['result'], 16)


async def get_nonce(session, sem, rpcs, addr):
    r = await rpc_call(session, sem, rpcs, 'eth_getTransactionCount', [addr, 'latest'])
    if not r or 'result' not in r or not r['result']:
        return 0
    return int(r['result'], 16)


async def main():
    chains = json.load(open(os.path.join(SCRIPT_DIR, 'data', 'chains.json')))['chains']
    rpcs = chains['ethereum']['rpcs']
    sem = asyncio.Semaphore(20)
    ssl_ctx = ssl.create_default_context(cafile=certifi.where())
    connector = aiohttp.TCPConnector(limit=40, ssl=ssl_ctx)

    async with aiohttp.ClientSession(connector=connector) as session:
        # PHASE 1: scan all 10,000 punk bid slots
        print('=' * 90)
        print('  PHASE 1: Scanning all 10,000 punkBids[] for active bids')
        print('=' * 90)

        t0 = time.time()
        active_bids = []
        BATCH = 50
        for batch_start in range(0, 10000, BATCH):
            tasks = [get_punk_bid(session, sem, rpcs, V2, i)
                     for i in range(batch_start, min(batch_start + BATCH, 10000))]
            results = await asyncio.gather(*tasks)
            for r in results:
                if r and r['hasBid'] and r['value'] > 0:
                    active_bids.append(r)
            if batch_start % 1000 == 0:
                elapsed = time.time() - t0
                total = sum(b['value'] for b in active_bids)
                print(f'  ...punks {batch_start:>5}/10000  active_bids={len(active_bids)}  '
                      f'sum={total/1e18:,.2f} ETH  ({elapsed:.0f}s)', flush=True)

        elapsed = time.time() - t0
        bids_total = sum(b['value'] for b in active_bids) / 1e18
        print(f'\n  Done in {elapsed:.0f}s')
        print(f'  Active bids found: {len(active_bids)}')
        print(f'  Total ETH locked in bids: {bids_total:,.4f}')

        # PHASE 2: load existing pendingWithdrawals
        print('\n' + '=' * 90)
        print('  PHASE 2: Combining with pendingWithdrawals (94 addresses)')
        print('=' * 90)
        cp_path = os.path.join(SCRIPT_DIR, 'results', 'cryptopunks_pending.json')
        pendings = json.load(open(cp_path))

        total_per_addr = {}
        for p in pendings:
            addr = p['seller'].lower()
            total_per_addr.setdefault(addr, {'pending': 0, 'bids': [], 'address': addr})
            total_per_addr[addr]['pending'] += p['pending_eth']

        for b in active_bids:
            addr = b['bidder'].lower()
            total_per_addr.setdefault(addr, {'pending': 0, 'bids': [], 'address': addr})
            total_per_addr[addr]['bids'].append({
                'punk': b['punkIndex'],
                'value_eth': b['value'] / 1e18,
            })

        for entry in total_per_addr.values():
            entry['bids_total'] = sum(b['value_eth'] for b in entry['bids'])
            entry['recoverable_total'] = entry['pending'] + entry['bids_total']

        recoverable = sorted(total_per_addr.values(),
                             key=lambda x: -x['recoverable_total'])

        print(f'  Total distinct recoverable addresses: {len(recoverable)}')
        grand = sum(e['recoverable_total'] for e in recoverable)
        print(f'  Grand total recoverable: {grand:,.4f} ETH')

        # PHASE 3: classify EOA vs contract for top candidates
        print('\n' + '=' * 90)
        print('  PHASE 3: Classifying top 50 (EOA vs Contract + activity)')
        print('=' * 90)

        top = recoverable[:50]
        for i in range(0, len(top), 10):
            chunk = top[i:i+10]
            tasks = []
            for entry in chunk:
                tasks.append(asyncio.gather(
                    get_code_size(session, sem, rpcs, entry['address']),
                    get_balance(session, sem, rpcs, entry['address']),
                    get_nonce(session, sem, rpcs, entry['address']),
                ))
            results = await asyncio.gather(*tasks)
            for entry, (cs, bal, nonce) in zip(chunk, results):
                entry['code_size'] = cs
                entry['is_contract'] = cs > 0
                entry['eoa_balance'] = bal / 1e18
                entry['eoa_nonce'] = nonce

        print(f'\n{"#":>3}  {"recoverable":>14}  {"address":<44}  {"type":<8}  '
              f'{"bal":>10}  {"nonce":>7}  detail')
        print('-' * 130)
        eoa_count = 0
        contract_count = 0
        dormant_eoas = []
        for i, e in enumerate(top):
            kind = 'CONTRACT' if e['is_contract'] else 'EOA'
            if e['is_contract']:
                contract_count += 1
            else:
                eoa_count += 1
                if e['eoa_balance'] < 0.001 and e['eoa_nonce'] < 5:
                    dormant_eoas.append(e)

            details = []
            if e['pending'] > 0:
                details.append(f"pending={e['pending']:.2f}")
            if e['bids']:
                details.append(f"bids={len(e['bids'])}({e['bids_total']:.2f})")

            print(f"{i+1:>3}  {e['recoverable_total']:>14,.4f}  {e['address']}  "
                  f"{kind:<8}  {e.get('eoa_balance', 0):>10,.4f}  "
                  f"{e.get('eoa_nonce', 0):>7}  {', '.join(details)}")

        # PHASE 4: summary
        print('\n' + '=' * 90)
        print('  PHASE 4: SUMMARY')
        print('=' * 90)
        print(f'  Total recoverable addresses (bids + pending): {len(recoverable)}')
        print(f'  Total ETH recoverable:                        {grand:,.4f}')
        print(f'  In top 50: EOAs={eoa_count}, Contracts={contract_count}')
        print(f'  Truly DORMANT EOAs in top 50 (bal<0.001, nonce<5): {len(dormant_eoas)}')

        if dormant_eoas:
            print(f'\n  *** DORMANT EOAs - likely lost-key addresses ***')
            for e in dormant_eoas[:20]:
                print(f"    {e['recoverable_total']:>10,.4f} ETH  {e['address']}  "
                      f"(bal={e['eoa_balance']:.4f}, nonce={e['eoa_nonce']})")

        # Save
        out = os.path.join(SCRIPT_DIR, 'results', 'cryptopunks_full_recoverable.json')
        clean = []
        for e in recoverable:
            clean.append({
                'address': e['address'],
                'pending_eth': e['pending'],
                'bids_total_eth': e['bids_total'],
                'recoverable_total': e['recoverable_total'],
                'bids': e['bids'],
                'is_contract': e.get('is_contract'),
                'code_size': e.get('code_size'),
                'eoa_balance': e.get('eoa_balance'),
                'eoa_nonce': e.get('eoa_nonce'),
            })
        json.dump(clean, open(out, 'w'), indent=2)
        print(f'\n[*] Saved: {out}')


if __name__ == '__main__':
    asyncio.run(main())
