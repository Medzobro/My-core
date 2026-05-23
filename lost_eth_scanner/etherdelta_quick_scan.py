#!/usr/bin/env python3
"""
EtherDelta / ForkDelta v3 - quick unclaimed balance scan.
Strategy: enumerate Deposit events with smaller block chunks for stability.
"""
import asyncio, json, os, ssl, time, sys
import aiohttp, certifi

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

CONTRACT = '0x8d12A197cB00D4747a1fe03395095ce2A5CC6819'
DEPOSIT_TOPIC = '0xdcbc1c05240f31ff3ad067ef1ee35ce4997762752e3a095284754544f4c709d7'
BAL_SEL = '0xf7888aec'

# Block range: ETH ICO mania 2017-12 to 2018-04 (peak ED activity)
START_BLOCK = int(sys.argv[1]) if len(sys.argv) > 1 else 4700000
END_BLOCK   = int(sys.argv[2]) if len(sys.argv) > 2 else 4900000


def encode_addr(a):
    return ('0' * 24) + a.lower().replace('0x', '')


async def rpc_call(session, sem, rpcs, method, params, timeout=30.0):
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
                    if 'error' in data:
                        # often "block range too large"; let caller back off
                        return None
            except Exception:
                continue
    return None


async def scan_blocks(session, sem, rpcs, start, end):
    users = set()
    cur = start
    step = 50000
    while cur < end:
        seg_end = min(cur + step, end)
        params = [{
            'fromBlock': hex(cur), 'toBlock': hex(seg_end),
            'address': CONTRACT, 'topics': [DEPOSIT_TOPIC],
        }]
        logs = await rpc_call(session, sem, rpcs, 'eth_getLogs', params)
        if isinstance(logs, list):
            for lg in logs:
                d = lg.get('data', '0x')
                if len(d) >= 2 + 64 * 4:
                    raw = d[2:]
                    user = '0x' + raw[64 + 24:64 + 64]
                    if int(user, 16) > 0:
                        users.add(user.lower())
            print(f'  blocks {cur:>10}-{seg_end:>10}: +{len(logs)} logs, users={len(users)}', flush=True)
            cur = seg_end + 1
        else:
            step = max(10000, step // 2)
            print(f'  step -> {step}', flush=True)
            await asyncio.sleep(0.3)
    return users


async def query_balance(session, sem, rpcs, user):
    data = BAL_SEL + encode_addr('0x0000000000000000000000000000000000000000') + encode_addr(user)
    r = await rpc_call(session, sem, rpcs, 'eth_call',
                       [{'to': CONTRACT, 'data': data}, 'latest'])
    if r and r != '0x':
        try: return int(r, 16)
        except: return 0
    return 0


async def main():
    chains = json.load(open(os.path.join(SCRIPT_DIR, 'data', 'chains.json')))['chains']
    rpcs = chains['ethereum']['rpcs']
    sem = asyncio.Semaphore(20)
    ssl_ctx = ssl.create_default_context(cafile=certifi.where())
    connector = aiohttp.TCPConnector(limit=40, ssl=ssl_ctx)

    print(f'[*] EtherDelta v3 scan blocks {START_BLOCK:,} -> {END_BLOCK:,}', flush=True)
    t0 = time.time()
    async with aiohttp.ClientSession(connector=connector) as session:
        users = await scan_blocks(session, sem, rpcs, START_BLOCK, END_BLOCK)
        print(f'\n[*] {len(users)} unique users in {time.time()-t0:.1f}s', flush=True)

        users_l = list(users)
        results = []
        BATCH = 300
        t1 = time.time()
        for i in range(0, len(users_l), BATCH):
            chunk = users_l[i:i+BATCH]
            balances = await asyncio.gather(*[query_balance(session, sem, rpcs, u) for u in chunk])
            for u, b in zip(chunk, balances):
                if b > 0:
                    results.append((u, b))
            if i % 600 == 0 and i > 0:
                total = sum(b for _, b in results) / 1e18
                print(f'  [{i}/{len(users_l)}]  found={len(results)}  sum={total:,.2f} ETH', flush=True)

        results.sort(key=lambda x: -x[1])
        total = sum(b for _, b in results) / 1e18
        print(f'\n=== ETHERDELTA v3 RESULTS ({START_BLOCK}-{END_BLOCK}) ===')
        print(f'  Users with balance: {len(results)} of {len(users_l)} scanned')
        print(f'  Total unclaimed:    {total:,.4f} ETH (~${total*2500:,.0f})')
        print(f'\n  TOP 30:')
        for u, b in results[:30]:
            print(f"    {b/1e18:>12,.4f} ETH  {u}")

        out = os.path.join(SCRIPT_DIR, f'etherdelta_unclaimed_{START_BLOCK}_{END_BLOCK}.json')
        json.dump([{'user': u, 'eth': b/1e18, 'wei': str(b)} for u, b in results],
                  open(out, 'w'), indent=2)
        print(f'\n[*] Saved: {out}')


if __name__ == '__main__':
    asyncio.run(main())
