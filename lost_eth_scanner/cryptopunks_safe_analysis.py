#!/usr/bin/env python3
"""
The 5 contracts holding CryptoPunks pendingWithdrawals are Gnosis Safe wallets!
Selector 0xa619486e = masterCopy() = Gnosis Safe Proxy pattern.

This script:
  1. Queries getOwners(), getThreshold(), nonce() on each Safe
  2. Checks each owner's activity to find dormant owners
  3. Reports if any Safe is 1-of-1 with a dormant owner (lost-key candidate)
"""
import asyncio
import json
import os
import ssl

import aiohttp
import certifi

RPC = 'https://ethereum-rpc.publicnode.com'

SAFES = [
    ('0xcafbf7952763c7237d2848a553e3146cbdd08602', 103.35),
    ('0x47452c970e08bf7105c753b798536e685e042231', 28.89),
    ('0x3bb0fe1d19e1f10a457cd3d26cd0db78dfdd677e', 0.8),  # NOT a Safe (EOF format)
    ('0xc50673edb3a7b94e8cad8a7d4e0cd68864e33edf', 0),
    ('0xd5ef7d3d225770bcfc4a46f9cef413f440610dee', 0),
]

# Gnosis Safe selectors
GET_OWNERS = '0xa0e67e2b'
GET_THRESHOLD = '0xe75235b8'
NONCE = '0xaffed0e0'  # nonce() on Safe
GET_VERSION = '0xffa1ad74'  # VERSION()


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


def decode_address_array(hex_data):
    """Decode bytes32[] returned by getOwners(): offset, length, data..."""
    if not hex_data or hex_data == '0x':
        return []
    raw = hex_data[2:]
    if len(raw) < 128:
        return []
    # Skip offset (32 bytes), then length (32 bytes), then addresses
    length = int(raw[64:128], 16)
    addresses = []
    for i in range(length):
        start = 128 + i * 64
        addr = '0x' + raw[start + 24:start + 64]
        addresses.append(addr)
    return addresses


async def analyze_safe(addr, pending):
    print(f'\n{"=" * 80}')
    print(f'  SAFE: {addr}  (pending: {pending} ETH)')
    print('=' * 80)

    # First read storage slot 0 to confirm it's a Safe Proxy
    storage = await call('eth_getStorageAt', [addr, '0x0', 'latest'])
    if storage and 'result' in storage:
        v = storage['result']
        if v != '0x' and len(v) >= 66:
            impl = '0x' + v[-40:]
            print(f'  Implementation (slot 0): {impl}')

    # Try getOwners()
    print(f'\n  Querying Safe state:')

    # getOwners
    r = await call('eth_call', [{'to': addr, 'data': GET_OWNERS}, 'latest'])
    owners = []
    if r and 'result' in r and r['result'] and r['result'] != '0x':
        owners = decode_address_array(r['result'])
        print(f'    Owners ({len(owners)}):')
        for o in owners:
            print(f'      {o}')

    # getThreshold
    r = await call('eth_call', [{'to': addr, 'data': GET_THRESHOLD}, 'latest'])
    threshold = 0
    if r and 'result' in r and r['result'] and r['result'] != '0x':
        try:
            threshold = int(r['result'], 16)
            print(f'    Threshold: {threshold} of {len(owners)}')
        except Exception:
            pass

    # nonce
    r = await call('eth_call', [{'to': addr, 'data': NONCE}, 'latest'])
    safe_nonce = 0
    if r and 'result' in r and r['result'] and r['result'] != '0x':
        try:
            safe_nonce = int(r['result'], 16)
            print(f'    Safe nonce (txs executed): {safe_nonce}')
        except Exception:
            pass

    # VERSION
    r = await call('eth_call', [{'to': addr, 'data': GET_VERSION}, 'latest'])
    if r and 'result' in r and r['result'] and r['result'] != '0x':
        try:
            # decode string
            raw = r['result'][2:]
            length = int(raw[64:128], 16)
            version_bytes = bytes.fromhex(raw[128:128 + length * 2])
            print(f'    Version: {version_bytes.decode("utf-8", errors="replace")}')
        except Exception:
            pass

    # Now check each owner's activity
    if owners:
        print(f'\n  Owner activity:')
        for o in owners:
            bal_r = await call('eth_getBalance', [o, 'latest'])
            nonce_r = await call('eth_getTransactionCount', [o, 'latest'])
            code_r = await call('eth_getCode', [o, 'latest'])

            bal = int(bal_r['result'], 16) / 1e18 if bal_r and 'result' in bal_r and bal_r['result'] else 0
            nonce = int(nonce_r['result'], 16) if nonce_r and 'result' in nonce_r and nonce_r['result'] else 0
            code_size = (len(code_r['result']) - 2) // 2 if code_r and 'result' in code_r and code_r['result'] and code_r['result'] != '0x' else 0

            kind = 'CONTRACT' if code_size > 0 else 'EOA'
            status = ''
            if code_size == 0 and nonce == 0 and bal < 0.001:
                status = ' >>> DORMANT (lost-key candidate!)'
            elif nonce > 50:
                status = ' (active)'

            print(f'      {o}  type={kind:8s}  bal={bal:>10.4f}  nonce={nonce:>5}{status}')

    # Determine if this is a "1-of-1 with dormant owner" candidate
    if threshold == 1 and len(owners) == 1:
        # Check if the single owner is dormant
        only_owner = owners[0]
        bal_r = await call('eth_getBalance', [only_owner, 'latest'])
        nonce_r = await call('eth_getTransactionCount', [only_owner, 'latest'])
        bal = int(bal_r['result'], 16) / 1e18 if bal_r and 'result' in bal_r and bal_r['result'] else 0
        nonce = int(nonce_r['result'], 16) if nonce_r and 'result' in nonce_r and nonce_r['result'] else 0
        if nonce == 0 and bal < 0.001:
            print(f'\n  *** 1-OF-1 SAFE WITH DORMANT OWNER ***')
            print(f'  *** The sole owner ({only_owner}) appears to be lost-key. ***')
            print(f'  *** {pending} ETH is effectively unrecoverable. ***')


async def main():
    for addr, pending in SAFES:
        if pending > 0:
            await analyze_safe(addr, pending)


if __name__ == '__main__':
    asyncio.run(main())
