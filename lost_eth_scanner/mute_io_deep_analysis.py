#!/usr/bin/env python3
"""
Deep analysis of Mute.io Router on zkSync to determine if its 7.17 ETH
balance is actually drainable via the SELFDESTRUCT bytes found.

The 152K eth_estimateGas number is suspicious - on zkSync, this is
ALMOST EXACTLY the L1 pubdata cost (130K-150K) for any state-changing tx.
That alone doesn't prove the function does real work.

We test:
  1. Read the contract's storage to find owner/admin
  2. Identify if it's a proxy
  3. Try calling via different signatures with DIFFERENT senders
  4. Compare gas estimates - if they're all identical regardless of args,
     it's a fallback/proxy (no real differentiation)
  5. Check Sourcify for verified source
"""
import asyncio
import json
import os
import ssl

import aiohttp
import certifi

ADDR = '0x8B791913eB07C32779a16750e3868aA8495F5964'  # Mute.io Router
RPC = 'https://mainnet.era.zksync.io'


async def call(method, params, timeout=20):
    payload = {'jsonrpc': '2.0', 'method': method, 'params': params, 'id': 1}
    ctx = ssl.create_default_context(cafile=certifi.where())
    async with aiohttp.ClientSession(connector=aiohttp.TCPConnector(ssl=ctx)) as s:
        try:
            async with s.post(RPC, json=payload,
                             timeout=aiohttp.ClientTimeout(total=timeout)) as r:
                return await r.json()
        except Exception as e:
            return {'error': str(e)}


async def main():
    print('=' * 80)
    print(f'  MUTE.IO ROUTER DEEP ANALYSIS (zkSync Era)')
    print(f'  {ADDR}')
    print('=' * 80)

    # 1. Balance
    r = await call('eth_getBalance', [ADDR, 'latest'])
    if r and 'result' in r:
        print(f'\n  Balance: {int(r["result"], 16) / 1e18:,.6f} ETH')

    # 2. Get code
    r = await call('eth_getCode', [ADDR, 'latest'])
    if not r or 'result' not in r:
        print('  Cannot fetch code')
        return
    code = r['result']
    print(f'  Code size: {(len(code) - 2) // 2:,} bytes')

    # Check if it's a proxy via EIP-1967
    EIP1967_IMPL = '0x360894a13ba1a3210667c828492db98dca3e2076cc3735a920a3ca505d382bbc'
    EIP1967_ADMIN = '0xb53127684a568b3173ae13b9f8a6016e243e63b6e8ee1178d6a717850b5d6103'

    impl_r = await call('eth_getStorageAt', [ADDR, EIP1967_IMPL, 'latest'])
    admin_r = await call('eth_getStorageAt', [ADDR, EIP1967_ADMIN, 'latest'])

    if impl_r and 'result' in impl_r:
        v = impl_r['result']
        if v != '0x' and len(v) >= 66 and int(v, 16) > 1:
            impl_addr = '0x' + v[-40:]
            print(f'\n  *** EIP-1967 PROXY DETECTED!')
            print(f'  Implementation: {impl_addr}')
        else:
            print(f'\n  Not EIP-1967 (impl slot empty)')

    if admin_r and 'result' in admin_r:
        v = admin_r['result']
        if v != '0x' and len(v) >= 66 and int(v, 16) > 1:
            admin_addr = '0x' + v[-40:]
            print(f'  Admin:          {admin_addr}')

    # 3. Read first 10 storage slots
    print(f'\n  First 10 storage slots:')
    for slot in range(10):
        r = await call('eth_getStorageAt', [ADDR, hex(slot), 'latest'])
        if r and 'result' in r and r['result']:
            v = r['result']
            if v == '0x' + '0' * 64:
                continue
            int_val = int(v, 16)
            if int_val > 0:
                # Try interpret as address
                if int_val > 0 and int_val < 2**160:
                    addr = '0x' + v[-40:]
                    print(f'    slot {slot}: {v[:34]}...  -> addr={addr}')
                else:
                    print(f'    slot {slot}: {v[:34]}...  uint={int_val}')

    # 4. Probe a wide variety of selectors with eth_estimateGas
    print(f'\n  Gas estimates for various functions (from random EOA):')
    test_from = '0xCafeBabeCafeBabeCafeBabeCafeBabeCafeBabe'
    selectors = {
        # Drain-style
        '3ccfd60b': 'withdraw()',
        '853828b6': 'withdrawAll()',
        'e9fad8ee': 'exit()',
        '4ae53a7c': 'sweep()',
        '01681a62': 'sweep(address)',
        'c30436e9': 'rescue()',
        'b95459e4': 'rescueETH()',
        '6a385ae9': 'rescueTokens(address,uint256)',
        'a430a05a': 'recover()',
        'a64f0bb9': 'recoverETH()',
        'db006a75': 'redeem()',
        # Kill-style
        '41c0e1b5': 'kill()',
        '35f46994': 'destroy()',
        '9cb8a26a': 'destruct()',
        '5e80fe79': 'suicide()',
        # Mute.io specific (router functions - would NOT be drainable but show real work)
        '7ff36ab5': 'swapExactETHForTokens(uint256,address[],address,uint256)',
        '38ed1739': 'swapExactTokensForTokens(uint256,uint256,address[],address,uint256)',
        # WETH-style for weth on zkSync
        'd0e30db0': 'deposit()',  # payable - just to see
        # Proxy admin functions
        '8129fc1c': 'initialize()',
        '3659cfe6': 'upgradeTo(address)',
        # No matching function
        'deadbeef': 'unknown()',
    }

    gas_results = {}
    for sel, name in selectors.items():
        cd = '0x' + sel
        if 'address' in name and '(' in name:
            cd += '0' * 24 + test_from[2:].lower()
        elif 'uint256' in name:
            cd += '0' * 64
        r = await call('eth_estimateGas',
                       [{'from': test_from, 'to': ADDR, 'data': cd, 'value': '0x0'}])
        if r and 'result' in r and r['result']:
            try:
                g = int(r['result'], 16)
                gas_results[name] = g
                marker = ''
                if g > 50000:
                    marker = ' [HIGH]'
                if g < 30000:
                    marker = ' [LOW - fallback]'
                print(f'    {name:55s} gas={g:>8}{marker}')
            except Exception:
                pass
        elif r and 'error' in r:
            err = r['error']
            msg = err.get('message', '') if isinstance(err, dict) else str(err)
            print(f'    {name:55s} REVERT: {msg[:60]}')

    # If all gas estimates are identical, the contract has a generic fallback
    unique_gases = set(gas_results.values())
    print(f'\n  Distinct gas amounts: {len(unique_gases)} ({sorted(unique_gases)})')
    if len(unique_gases) <= 2:
        print('  >>> All functions consume the same gas - this is a GENERIC FALLBACK.')
        print('  >>> The 152K estimate is just zkSync L1 pubdata overhead.')
        print('  >>> The contract is NOT actually executing kill/withdraw logic.')
        print('  >>> SELFDESTRUCT bytes in code are likely in metadata, unreachable.')

    # 5. Try Sourcify for verified source
    print(f'\n  Checking Sourcify for verified source...')
    sourcify_url = f'https://sourcify.dev/server/files/any/324/{ADDR.lower()}'
    ctx = ssl.create_default_context(cafile=certifi.where())
    async with aiohttp.ClientSession(connector=aiohttp.TCPConnector(ssl=ctx)) as s:
        try:
            async with s.get(sourcify_url, timeout=aiohttp.ClientTimeout(total=15)) as r:
                if r.status == 200:
                    d = await r.json()
                    print(f'    Found! Files: {len(d.get("files", []))}')
                    for f in d.get('files', [])[:5]:
                        if isinstance(f, dict):
                            name = f.get('name', '?')
                            content = f.get('content', '')
                            print(f'      {name} ({len(content)} bytes)')
                            if 'selfdestruct' in content.lower() or 'kill' in content.lower():
                                print(f'        !! contains selfdestruct/kill keyword')
                else:
                    print(f'    Not found (HTTP {r.status})')
        except Exception as e:
            print(f'    Error: {e}')


if __name__ == '__main__':
    asyncio.run(main())
