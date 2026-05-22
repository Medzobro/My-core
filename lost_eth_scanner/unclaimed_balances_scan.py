#!/usr/bin/env python3
"""
UNCLAIMED USER BALANCES SCANNER (faster, save-as-we-go)
========================================================
Reduced timeframes & batch sizes for tractable runtime.
"""
import asyncio, json, os, ssl, time, sys
import aiohttp, certifi

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

TARGETS = [
    {
        'name': 'ForkDelta / EtherDelta v3',
        'address': '0x8d12A197cB00D4747a1fe03395095ce2A5CC6819',
        'balance_selector': '0xf7888aec',
        'deposit_topic': '0xdcbc1c05240f31ff3ad067ef1ee35ce4997762752e3a095284754544f4c709d7',
        'from_block': 4170000,
        'to_block':   8000000,  # late 2019; activity peaked 2017-2018
    },
    {
        'name': 'IDEX 1.0',
        'address': '0x2a0c0DBEcC7E4D658f48E01e3fA353F44050c208',
        'balance_selector': '0xf7888aec',
        'deposit_topic': '0xdcbc1c05240f31ff3ad067ef1ee35ce4997762752e3a095284754544f4c709d7',
        'from_block': 4500000,
        'to_block':   10000000,  # mid 2020
    },
    {
        'name': 'Token.Store',
        'address': '0x1ce7AE555139c5EF5A57CC8d814a867ee6Ee33D8',
        'balance_selector': '0xf7888aec',
        'deposit_topic': '0xdcbc1c05240f31ff3ad067ef1ee35ce4997762752e3a095284754544f4c709d7',
        'from_block': 4800000,
        'to_block':   8500000,
    },
]


def encode_addr(a):
    return ('0' * 24) + a.lower().replace('0x', '')


async def rpc_call(session, sem, rpcs, method, params, timeout=20.0):
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


async def get_logs_chunk(session, sem, rpcs, contract, topic, start, end):
    params = [{
        'fromBlock': hex(start), 'toBlock': hex(end),
        'address': contract, 'topics': [topic],
    }]
    return await rpc_call(session, sem, rpcs, 'eth_getLogs', params, timeout=30.0)


async def enumerate_users(session, sem, rpcs, contract, topic, start, end, step=200000):
    users = set()
    cur = start
    while cur < end:
        seg_end = min(cur + step, end)
        logs = await get_logs_chunk(session, sem, rpcs, contract, topic, cur, seg_end)
        if isinstance(logs, list):
            for lg in logs:
                data = lg.get('data', '0x')
                if len(data) >= 2 + 64 * 4:
                    raw = data[2:]
                    user = '0x' + raw[64 + 24:64 + 64]
                    if int(user, 16) > 0:
                        users.add(user.lower())
            print(f'    blocks {cur:>10}-{seg_end:>10}: +{len(logs)} events, {len(users)} unique users so far')
            sys.stdout.flush()
            cur = seg_end + 1
        else:
            if step > 50000:
                step //= 2
            else:
                cur = seg_end + 1
    return users


async def query_balance(session, sem, rpcs, contract, user, sel):
    data = sel + encode_addr('0x0000000000000000000000000000000000000000') + encode_addr(user)
    r = await rpc_call(session, sem, rpcs, 'eth_call',
                       [{'to': contract, 'data': data}, 'latest'])
    if r and r != '0x':
        try: return int(r, 16)
        except: return 0
    return 0


async def scan_one(session, sem, rpcs, target, save_progress=True):
    name = target['name']
    addr = target['address']
    print(f'\n=== {name}  ({addr}) ===')

    # Cache file
    users_file = os.path.join(SCRIPT_DIR, f'users_{addr.lower()}.json')
    if os.path.exists(users_file):
        users = set(json.load(open(users_file)))
        print(f'  Loaded {len(users)} cached users')
    else:
        t0 = time.time()
        users = await enumerate_users(session, sem, rpcs, addr, target['deposit_topic'],
                                        target['from_block'], target['to_block'])
        print(f'  -> {len(users)} unique users in {time.time()-t0:.1f}s')
        if save_progress:
            json.dump(list(users), open(users_file, 'w'))

    # Query balances in parallel batches
    user_list = list(users)
    sel = target['balance_selector']
    print(f'  Querying balances for {len(user_list)} users...')
    t0 = time.time()
    balances = []
    BATCH = 200
    for i in range(0, len(user_list), BATCH):
        chunk = user_list[i:i + BATCH]
        chunk_b = await asyncio.gather(*[query_balance(session, sem, rpcs, addr, u, sel) for u in chunk])
        balances.extend(chunk_b)
        if i % 1000 == 0:
            elapsed = time.time() - t0
            non_zero = sum(1 for b in balances if b > 0)
            total = sum(balances) / 1e18
            print(f'    [{i:>5}/{len(user_list)}] non_zero={non_zero}, sum={total:,.2f} ETH ({elapsed:.0f}s)')
            sys.stdout.flush()

    nonzero = [(u, b) for u, b in zip(user_list, balances) if b > 0]
    nonzero.sort(key=lambda x: -x[1])
    total_eth = sum(b for _, b in nonzero) / 1e18

    print(f'  RESULT: {len(nonzero)} addresses with balance, total = {total_eth:,.4f} ETH')

    return {
        'name': name,
        'address': addr,
        'n_users': len(users),
        'n_with_balance': len(nonzero),
        'total_eth': total_eth,
        'top': [{'user': u, 'eth': b/1e18, 'wei': str(b)} for u, b in nonzero[:50]],
    }


async def main():
    chains = json.load(open(os.path.join(SCRIPT_DIR, 'chains.json')))['chains']
    rpcs = chains['ethereum']['rpcs']
    sem = asyncio.Semaphore(20)
    ssl_ctx = ssl.create_default_context(cafile=certifi.where())
    connector = aiohttp.TCPConnector(limit=40, ssl=ssl_ctx)

    out_file = os.path.join(SCRIPT_DIR, 'unclaimed_balances.json')
    all_results = []

    async with aiohttp.ClientSession(connector=connector) as session:
        for t in TARGETS:
            try:
                r = await scan_one(session, sem, rpcs, t)
                all_results.append(r)
                # Save after each target
                json.dump(all_results, open(out_file, 'w'), indent=2)
                print(f'  [persisted to {out_file}]')
            except Exception as e:
                print(f'  ERROR: {e}')
                import traceback; traceback.print_exc()

    print('\n' + '=' * 90)
    print('  FINAL REPORT')
    print('=' * 90)
    grand = 0
    for r in all_results:
        grand += r['total_eth']
        print(f"\n[{r['name']}]   {r['n_with_balance']:,} addresses, {r['total_eth']:,.4f} ETH")
        for entry in r['top'][:10]:
            print(f"  {entry['eth']:>12,.4f} ETH  {entry['user']}")
    print(f'\nGRAND TOTAL: {grand:,.4f} ETH ~${grand*2500:,.0f}')


if __name__ == '__main__':
    asyncio.run(main())
