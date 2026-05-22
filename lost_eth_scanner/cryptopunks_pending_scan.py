#!/usr/bin/env python3
"""
Scan CryptoPunks pendingWithdrawals[] for unclaimed seller balances.

Strategy:
  1. Pull all PunkBought events from both CryptoPunks contracts (V1, V2).
  2. For each unique seller, query pendingWithdrawals[seller].
  3. Report sellers with non-zero balance (= unclaimed ETH waiting for the seller's signature).

This won't yield "free money" for us, but reveals which historical addresses
hold withdraw-rights on the contract's 4.6 + 3,332 ETH balance.
"""
import asyncio, json, os, ssl, time
import aiohttp, certifi

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

CONTRACTS = {
    'V1_old_buggy': '0x6BA6f2207e343923BA692e5Cae646Fb0F566DB8D',
    'V2_current':   '0xb47e3cd837dDF8e4c57F05d70Ab865de6e193BBB',
}

# PunkBought event signature: PunkBought(uint256 indexed punkIndex, uint256 value, address indexed fromAddress, address indexed toAddress)
PUNK_BOUGHT_TOPIC = '0x58e5d5a525e3b40bc15abaa38b5882678db1ee68befd2f60bafe3a7fd06db9e3'

# pendingWithdrawals(address) selector
PENDING_WITHDRAWALS_SEL = '0xf3f43703'  # bytes4 keccak256("pendingWithdrawals(address)")


def addr_topic(a):
    return '0x' + ('0' * 24) + a.lower().replace('0x', '')


async def rpc_call(session, sem, rpcs, method, params, timeout=15.0):
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


async def get_logs_paginated(session, sem, rpcs, addr, topic, from_block=4500000, to_block=None, step=500000):
    """Fetch event logs in chunks to avoid RPC limits."""
    if to_block is None:
        latest = await rpc_call(session, sem, rpcs, 'eth_blockNumber', [])
        to_block = int(latest, 16) if latest else 19000000

    logs = []
    cur = from_block
    while cur < to_block:
        end = min(cur + step, to_block)
        params = [{
            'fromBlock': hex(cur),
            'toBlock': hex(end),
            'address': addr,
            'topics': [topic],
        }]
        r = await rpc_call(session, sem, rpcs, 'eth_getLogs', params, timeout=30.0)
        if isinstance(r, list):
            logs.extend(r)
            print(f'  [{addr[:10]}] blocks {cur:>10} -> {end:>10}: +{len(r)} logs (total {len(logs)})')
            cur = end + 1
        else:
            # Halve the step on error
            if step > 50000:
                step //= 2
                print(f'  [{addr[:10]}] reducing step to {step}')
            else:
                cur = end + 1
    return logs


async def query_pending(session, sem, rpcs, contract_addr, user_addr):
    data = PENDING_WITHDRAWALS_SEL + ('0' * 24) + user_addr.lower().replace('0x', '')
    r = await rpc_call(session, sem, rpcs, 'eth_call',
                       [{'to': contract_addr, 'data': data}, 'latest'])
    if r and r != '0x':
        try:
            return int(r, 16)
        except Exception:
            return 0
    return 0


async def main():
    chains = json.load(open(os.path.join(SCRIPT_DIR, 'chains.json')))['chains']
    rpcs = chains['ethereum']['rpcs']
    sem = asyncio.Semaphore(15)
    ssl_ctx = ssl.create_default_context(cafile=certifi.where())
    connector = aiohttp.TCPConnector(limit=30, ssl=ssl_ctx)

    async with aiohttp.ClientSession(connector=connector) as session:
        all_sellers = {}  # contract -> set of sellers
        for label, addr in CONTRACTS.items():
            print(f'\n[*] Fetching PunkBought logs from {label} ({addr})...')
            t0 = time.time()
            # Punks deployed around block 3914495 for V1, 3919706 for V2
            from_block = 3900000
            try:
                logs = await get_logs_paginated(session, sem, rpcs, addr, PUNK_BOUGHT_TOPIC,
                                                 from_block=from_block, step=1000000)
            except Exception as e:
                print(f'  failed: {e}')
                continue
            sellers = set()
            for lg in logs:
                topics = lg.get('topics', [])
                if len(topics) >= 3:
                    seller_topic = topics[2]  # fromAddress is indexed[2]
                    seller = '0x' + seller_topic[-40:]
                    sellers.add(seller.lower())
            print(f'  found {len(logs)} PunkBought events, {len(sellers)} unique sellers in {time.time()-t0:.1f}s')
            all_sellers[(label, addr)] = sellers

        # Now query pendingWithdrawals for each seller on each contract
        print('\n[*] Querying pendingWithdrawals[]...')
        results = []
        for (label, addr), sellers in all_sellers.items():
            print(f'\n  Contract {label} ({addr}), {len(sellers)} sellers:')
            tasks = [query_pending(session, sem, rpcs, addr, s) for s in sellers]
            balances = await asyncio.gather(*tasks)
            for s, b in zip(sellers, balances):
                if b > 0:
                    results.append({
                        'contract': label,
                        'contract_addr': addr,
                        'seller': s,
                        'pending_wei': b,
                        'pending_eth': b / 1e18,
                    })

        # Sort by amount desc
        results.sort(key=lambda r: -r['pending_wei'])
        print('\n' + '=' * 90)
        print('  CRYPTOPUNKS pendingWithdrawals - UNCLAIMED SELLER BALANCES')
        print('=' * 90)
        if not results:
            print('  (none) -- all sellers have already claimed')
        else:
            total = sum(r['pending_wei'] for r in results)
            print(f'  Total pending across all sellers: {total/1e18:,.4f} ETH (~${total/1e18 * 2500:,.0f})\n')
            for r in results[:30]:
                print(f"  {r['pending_eth']:>10,.4f} ETH  {r['seller']}  ({r['contract']})")
            if len(results) > 30:
                print(f"  ... and {len(results) - 30} more")

        out = os.path.join(SCRIPT_DIR, 'cryptopunks_pending.json')
        with open(out, 'w') as f:
            json.dump(results, f, indent=2)
        print(f'\n[*] Saved: {out}')


if __name__ == '__main__':
    asyncio.run(main())
