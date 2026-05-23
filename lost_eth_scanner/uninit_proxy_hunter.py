#!/usr/bin/env python3
"""
UNINITIALIZED PROXY HUNTER
===========================
Novel attack vector: search for proxy contracts that have funds AND whose
`initialize()` function was never called.

This is a real, well-known historical exploit pattern:
  - OpenZeppelin TransparentUpgradeableProxy / UUPS
  - Old custom proxies pre-2020 best practices
  - Front-running of initialize() in deploy txs

If we find one, ANYONE can call initialize() to become the admin/owner,
then call upgrade() / sweep() / setOwner() to drain.

Strategy:
  1. For each contract with native balance > 0
  2. Check if it has proxy bytecode patterns (DELEGATECALL to slot)
  3. Try calling each known initialize() variant via eth_call
  4. If call succeeds AND admin slot looks unset, it's a candidate
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

# OpenZeppelin storage slots (EIP-1967)
EIP1967_IMPL_SLOT = '0x360894a13ba1a3210667c828492db98dca3e2076cc3735a920a3ca505d382bbc'
EIP1967_ADMIN_SLOT = '0xb53127684a568b3173ae13b9f8a6016e243e63b6e8ee1178d6a717850b5d6103'

# Known initialize() selectors
INIT_SELECTORS = {
    '8129fc1c': 'initialize()',
    '4cd88b76': 'init()',
    'c4d66de8': 'initialize(address)',
    '485cc955': 'initialize(address,address)',
    'cf756fdf': 'initialize(address,address,address)',
    '6f2ddd93': 'initialize(address,address,address,address)',
    '8624c35c': 'initialize(address,bytes)',
    'da99cee5': 'initialize(string,string)',
    '1c1b8772': 'initialize(string,string,uint256)',
    '162094c4': 'init(address)',
    '10d1e85c': 'init(address,address)',
    '1459457a': 'initialize(address,uint256)',
    '4f1ef286': 'upgradeToAndCall(address,bytes)',
    '3659cfe6': 'upgradeTo(address)',
    'fe4b84df': 'initialize(uint256)',
    'cd6dc687': 'initialize(uint256,address)',
}

# Test from address (a random EOA)
TEST_FROM = '0xCafeBabeCafeBabeCafeBabeCafeBabeCafeBabe'


def encode_addr(a):
    return ('0' * 24) + a.lower().replace('0x', '')


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
                    if 'error' in d:
                        return {'error': d['error']}
                    return {'result': d.get('result')}
            except Exception:
                continue
    return None


async def is_proxy(session, sem, rpcs, addr) -> dict:
    """Check if the contract is a proxy (has EIP-1967 impl slot or DELEGATECALL bytecode)."""
    code_r = await rpc_call(session, sem, rpcs, 'eth_getCode', [addr, 'latest'])
    if not code_r or 'result' not in code_r:
        return {'is_proxy': False}
    code = code_r['result']
    if not code or code == '0x':
        return {'is_proxy': False, 'is_eoa': True}

    # Read EIP-1967 impl slot
    impl_r = await rpc_call(session, sem, rpcs, 'eth_getStorageAt',
                            [addr, EIP1967_IMPL_SLOT, 'latest'])
    admin_r = await rpc_call(session, sem, rpcs, 'eth_getStorageAt',
                             [addr, EIP1967_ADMIN_SLOT, 'latest'])

    impl = impl_r.get('result') if impl_r else None
    admin = admin_r.get('result') if admin_r else None

    # Also check raw delegate-call signature in bytecode
    has_delegatecall = 'f4' in code.lower()  # DELEGATECALL opcode
    code_size = (len(code) - 2) // 2

    impl_addr = None
    if impl and impl != '0x' and len(impl) >= 66:
        impl_int = int(impl, 16)
        if impl_int > 1:
            impl_addr = '0x' + impl[-40:]

    admin_addr = None
    if admin and admin != '0x' and len(admin) >= 66:
        admin_int = int(admin, 16)
        if admin_int > 1:
            admin_addr = '0x' + admin[-40:]

    # Tiny proxies (< 200 bytes) almost always pure-proxy (just delegatecall)
    is_minimal_proxy = code_size < 200 and has_delegatecall

    # Has EIP-1967 impl slot set
    is_eip1967 = impl_addr is not None

    return {
        'is_proxy': is_eip1967 or is_minimal_proxy,
        'is_eip1967': is_eip1967,
        'is_minimal': is_minimal_proxy,
        'impl_addr': impl_addr,
        'admin_addr': admin_addr,
        'code_size': code_size,
        'has_delegatecall': has_delegatecall,
    }


async def try_initialize(session, sem, rpcs, addr, sender):
    """Try every initialize selector. Return list of those that don't revert."""
    results = []
    for sel, sig in INIT_SELECTORS.items():
        # Build minimum-arg calldata
        if sig.endswith('()'):
            cd = '0x' + sel
        elif '(address)' in sig:
            cd = '0x' + sel + encode_addr(sender)
        elif '(address,address)' in sig:
            cd = '0x' + sel + encode_addr(sender) + encode_addr(sender)
        elif '(address,address,address)' in sig:
            cd = '0x' + sel + encode_addr(sender) * 3
        elif '(address,address,address,address)' in sig:
            cd = '0x' + sel + encode_addr(sender) * 4
        elif '(uint256)' in sig:
            cd = '0x' + sel + ('0' * 64)
        elif '(uint256,address)' in sig:
            cd = '0x' + sel + ('0' * 64) + encode_addr(sender)
        elif '(address,uint256)' in sig:
            cd = '0x' + sel + encode_addr(sender) + ('0' * 64)
        elif '(string,string)' in sig:
            cd = '0x' + sel + ('40'.rjust(64, '0')) + ('80'.rjust(64, '0')) + \
                 ('0' * 64) + ('0' * 64)
        elif '(string,string,uint256)' in sig:
            cd = '0x' + sel + ('60'.rjust(64, '0')) + ('a0'.rjust(64, '0')) + \
                 ('0' * 64) + ('0' * 64) + ('0' * 64)
        elif '(address,bytes)' in sig:
            cd = '0x' + sel + encode_addr(sender) + ('40'.rjust(64, '0')) + ('0' * 64)
        else:
            continue

        # eth_call simulation
        params = [{'from': sender, 'to': addr, 'data': cd, 'value': '0x0'}, 'latest']
        r = await rpc_call(session, sem, rpcs, 'eth_call', params)
        if r is None:
            continue
        if 'error' in r:
            err_msg = r['error'].get('message', '').lower()
            # Distinguish "already initialized" vs other reverts
            if 'already' in err_msg or 'initialized' in err_msg:
                results.append({'sig': sig, 'status': 'already_initialized', 'msg': err_msg[:80]})
            # Other reverts are noise
        else:
            # Simulation succeeded -> initialize is callable!
            # Now estimate gas to verify it's a real function
            gas_r = await rpc_call(session, sem, rpcs, 'eth_estimateGas',
                                   [{'from': sender, 'to': addr, 'data': cd, 'value': '0x0'}])
            gas = None
            if gas_r and 'result' in gas_r and gas_r['result']:
                try:
                    gas = int(gas_r['result'], 16)
                except Exception:
                    pass
            if gas and gas > 30000:
                results.append({'sig': sig, 'status': 'CALLABLE', 'gas': gas})
    return results


async def hunt_one(session, sem, rpcs, contract):
    addr = contract['address']
    bal_r = await rpc_call(session, sem, rpcs, 'eth_getBalance', [addr, 'latest'])
    if not bal_r or 'result' not in bal_r:
        return None
    bal = int(bal_r['result'], 16) if bal_r['result'] else 0
    if bal == 0:
        return None

    proxy_info = await is_proxy(session, sem, rpcs, addr)
    if not proxy_info.get('is_proxy'):
        return None

    init_results = await try_initialize(session, sem, rpcs, addr, TEST_FROM)
    callable_inits = [r for r in init_results if r['status'] == 'CALLABLE']
    if not callable_inits:
        return None

    return {
        'chain': contract['chain'],
        'name': contract.get('name', '?'),
        'address': addr,
        'category': contract.get('category', ''),
        'balance_eth': bal / 1e18,
        'proxy_info': proxy_info,
        'callable_initializes': callable_inits,
    }


async def main():
    chains = json.load(open(os.path.join(SCRIPT_DIR, 'data', 'chains.json')))['chains']
    contracts = json.load(open(os.path.join(SCRIPT_DIR, 'data', 'contracts_multichain.json')))['contracts']
    contracts = [c for c in contracts
                 if not c.get('_comment') and c.get('address', '').startswith('0x')]

    print(f'[*] Uninitialized Proxy Hunter: scanning {len(contracts)} contracts')
    print(f'[*] Looking for proxies where initialize() returns OK from random sender')

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
                    print(f"  *** {r['chain']:10s} bal={r['balance_eth']:>10,.4f}  "
                          f"{r['name'][:35]:35s} hits={len(r['callable_initializes'])}")

    elapsed = time.time() - t0
    candidates.sort(key=lambda r: -r['balance_eth'])

    print('\n' + '=' * 100)
    print('  UNINITIALIZED PROXY REPORT')
    print('=' * 100)
    print(f'  Scanned in {elapsed:.1f}s')
    print(f'  Found {len(candidates)} proxies with callable initialize functions\n')

    for i, r in enumerate(candidates[:20]):
        print(f"\n[{i+1}] {r['chain'].upper()}  {r['name']}")
        print(f"    contract:  {r['address']}")
        print(f"    balance:   {r['balance_eth']:,.4f} native")
        print(f"    proxy:     impl={r['proxy_info'].get('impl_addr')}")
        print(f"               admin={r['proxy_info'].get('admin_addr')}")
        print(f"               size={r['proxy_info'].get('code_size')} bytes")
        print(f"    callable initializes:")
        for ci in r['callable_initializes']:
            print(f"      => {ci['sig']:40s} gas={ci['gas']}")

    out = os.path.join(SCRIPT_DIR, 'results', 'uninit_proxy_results.json')
    os.makedirs(os.path.dirname(out), exist_ok=True)
    json.dump(candidates, open(out, 'w'), indent=2, default=str)
    print(f'\n[*] Saved: {out}')


if __name__ == '__main__':
    asyncio.run(main())
