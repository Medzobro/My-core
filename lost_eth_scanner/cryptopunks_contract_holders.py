#!/usr/bin/env python3
"""
DEEP DIVE: The 5 CONTRACTS that own pendingWithdrawals in CryptoPunks.

If a contract holds pendingWithdrawals but has no working `withdraw()` caller,
the funds are stuck UNLESS we find:
  1. A public function that triggers a CALL/DELEGATECALL we can exploit
  2. A forwarder pattern (executeArbitrary, multicall) callable by anyone
  3. A re-entrancy or initialization vulnerability
"""
import asyncio
import json
import os
import ssl
import urllib.request
import certifi

import aiohttp

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
RPC = 'https://ethereum-rpc.publicnode.com'


def encode_addr(a):
    return ('0' * 24) + a.lower().replace('0x', '')


async def call(method, params, timeout=15.0):
    payload = {'jsonrpc': '2.0', 'method': method, 'params': params, 'id': 1}
    ctx = ssl.create_default_context(cafile=certifi.where())
    async with aiohttp.ClientSession(connector=aiohttp.TCPConnector(ssl=ctx)) as s:
        try:
            async with s.post(RPC, json=payload,
                             timeout=aiohttp.ClientTimeout(total=timeout)) as r:
                return await r.json()
        except Exception as e:
            return {'error': str(e)}


def find_selectors(code_hex):
    """Find all 4-byte selectors in PUSH4 instructions."""
    if not code_hex or code_hex == '0x':
        return set()
    raw = code_hex[2:].lower()
    sels = set()
    i = 0
    while i < len(raw) - 10:
        if raw[i:i + 2] == '63':
            s = raw[i + 2:i + 10]
            if s != '00000000' and s != 'ffffffff':
                sels.add(s)
            i += 10
        else:
            i += 2
    return sels


# Common selector lookup
SELECTOR_NAMES = {
    '8da5cb5b': 'owner()',
    '893d20e8': 'getOwner()',
    'f851a440': 'admin()',
    '8129fc1c': 'initialize()',
    '4cd88b76': 'init()',
    '70a08231': 'balanceOf(address)',
    '23b872dd': 'transferFrom(address,address,uint256)',
    'a9059cbb': 'transfer(address,uint256)',
    '095ea7b3': 'approve(address,uint256)',
    '3ccfd60b': 'withdraw()',
    '2e1a7d4d': 'withdraw(uint256)',
    'e9fad8ee': 'exit()',
    'db006a75': 'redeem()',
    '4e71d92d': 'claim()',
    '4ae53a7c': 'sweep()',
    'c30436e9': 'rescue()',
    '6a385ae9': 'rescueTokens(address,uint256)',
    'b95459e4': 'rescueETH()',
    'a430a05a': 'recover()',
    'a64f0bb9': 'recoverETH()',
    'c7c19abf': 'recoverERC20(address,uint256)',
    'cea9d26f': 'rescue(address,uint256)',
    '01681a62': 'sweep(address)',
    '78cd1d56': 'collect()',
    '6b9f96ea': 'flush()',
    'd0a9405c': 'forward()',
    'fc6f7865': 'execute(address,uint256,bytes)',
    'b61d27f6': 'execute(address,uint256,bytes)',
    'ac9650d8': 'multicall(bytes[])',
    '5ae401dc': 'multicall(uint256,bytes[])',
    '1cff79cd': 'execute(address,bytes)',
    '5571a92e': 'invoke(address,uint256,bytes)',
    '5fcb6e8a': 'callContract(address,bytes)',
    '8c1ee9b9': 'doCall(address,bytes)',
    '5f8b1dba': 'arbitraryCall(address,bytes)',
    '41c0e1b5': 'kill()',
    '35f46994': 'destroy()',
    '9cb8a26a': 'destruct()',
    '1f7b6d32': 'forward(address,uint256,bytes)',
    'fec3a3df': 'callMethod(address,bytes)',
    '06fdde03': 'name()',
    '95d89b41': 'symbol()',
    '313ce567': 'decimals()',
    'd505accf': 'permit(address,address,uint256,uint256,uint8,bytes32,bytes32)',
    'f3fef3a3': 'withdraw(address,uint256)',
    'bedb86fb': 'pause(bool)',
    '5c975abb': 'paused()',
    'f2fde38b': 'transferOwnership(address)',
    '715018a6': 'renounceOwnership()',
    '24d7806c': 'isAdmin(address)',
    'fd1ad11c': 'addAdmin(address)',
    '7065cb48': 'addOwner(address)',
    '173825d9': 'removeOwner(address)',
    'b75c7dc6': 'revoke(bytes32)',
    'c01a8c84': 'confirmTransaction(uint256)',
    'c6427474': 'submitTransaction(address,uint256,bytes)',
    'a0e67e2b': 'getOwners()',
}


async def main():
    cp_path = os.path.join(SCRIPT_DIR, 'results', 'cryptopunks_corrected.json')
    if not os.path.exists(cp_path):
        print('Run cryptopunks_corrected_analysis.py first')
        return

    data = json.load(open(cp_path))
    contracts = [e for e in data if e.get('is_contract')]

    print('=' * 90)
    print(f'  CONTRACT HOLDERS OF CryptoPunks pendingWithdrawals')
    print(f'  Found {len(contracts)} contracts holding total '
          f'{sum(e["pending_eth"] for e in contracts):,.2f} ETH unclaimed')
    print('=' * 90)

    for i, c in enumerate(contracts):
        addr = c['address']
        print(f'\n--- [{i+1}/{len(contracts)}] {addr}  pending={c["pending_eth"]:,.4f} ETH ---')

        # Get full bytecode
        code_r = await call('eth_getCode', [addr, 'latest'])
        if not code_r or 'result' not in code_r:
            print('  Cannot fetch code')
            continue
        code = code_r['result']
        print(f'  Code size: {(len(code) - 2) // 2} bytes')

        # Find selectors
        sels = find_selectors(code)
        named = []
        unnamed = []
        for s in sels:
            if s in SELECTOR_NAMES:
                named.append((s, SELECTOR_NAMES[s]))
            else:
                unnamed.append(s)

        print(f'  Known function signatures ({len(named)}):')
        for s, name in sorted(named):
            print(f'    {s}: {name}')

        if unnamed:
            print(f'  Unknown selectors ({len(unnamed)}): {sorted(unnamed)[:10]}')

        # Read storage slots 0-9
        print(f'  Storage slots 0-9:')
        for slot in range(10):
            r = await call('eth_getStorageAt', [addr, hex(slot), 'latest'])
            if r and 'result' in r and r['result']:
                v = r['result']
                if v != '0x' + '0' * 64 and v != '0x':
                    int_val = int(v, 16)
                    if 0 < int_val < 2**160:
                        addr_form = '0x' + v[-40:]
                        print(f'    slot {slot}: {addr_form}  (looks like address)')
                    else:
                        print(f'    slot {slot}: {v}  (uint={int_val if int_val < 1e18 else "big"})')

        # Try owner() function
        print(f'  Owner check:')
        for sel in ('8da5cb5b', '893d20e8', 'f851a440'):
            if sel in sels:
                r = await call('eth_call', [{'to': addr, 'data': '0x' + sel}, 'latest'])
                if r and 'result' in r and r['result'] and r['result'] != '0x':
                    val = r['result']
                    if len(val) >= 66:
                        owner_addr = '0x' + val[-40:]
                        print(f'    {SELECTOR_NAMES[sel]} = {owner_addr}')
                        # Get owner's state
                        owner_state = await asyncio.gather(
                            call('eth_getBalance', [owner_addr, 'latest']),
                            call('eth_getTransactionCount', [owner_addr, 'latest']),
                        )
                        if owner_state[0] and 'result' in owner_state[0]:
                            ob = int(owner_state[0]['result'], 16) / 1e18
                            on = int(owner_state[1]['result'], 16) if owner_state[1] and 'result' in owner_state[1] else 0
                            print(f'      Owner balance: {ob:,.4f} ETH, nonce: {on}')

        # Test if generic "execute" / forwarder selectors are callable from random
        print(f'  Probing forwarder/execute functions from random EOA:')
        test_from = '0xCafeBabeCafeBabeCafeBabeCafeBabeCafeBabe'
        forwarder_sels = ['fc6f7865', 'b61d27f6', '1cff79cd', '5571a92e', '5fcb6e8a',
                          '8c1ee9b9', '5f8b1dba', '1f7b6d32', 'fec3a3df']
        for sel in forwarder_sels:
            if sel in sels:
                cd = '0x' + sel + encode_addr(addr) + ('0' * 64) + ('0' * 64)
                gas_r = await call('eth_estimateGas',
                                    [{'from': test_from, 'to': addr, 'data': cd, 'value': '0x0'}])
                if gas_r and 'result' in gas_r and gas_r['result']:
                    g = int(gas_r['result'], 16)
                    if g > 30000:
                        print(f'    *** {SELECTOR_NAMES.get(sel, sel)} gas={g}')


if __name__ == '__main__':
    asyncio.run(main())
