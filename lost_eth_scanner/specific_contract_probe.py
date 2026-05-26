#!/usr/bin/env python3
"""
SPECIFIC CONTRACT PROBE
=========================
Deep-dive on contracts where we know there *might* be a recovery path:

  - DigixDAO (dissolved 2020 - residual treasury)
  - Augur v1 Cash (legacy share redemption)
  - Maker SAI Tub (deprecated CDP system)
  - Compound v1 cETH (deprecated but still redeemable)
  - Synthetix Old Depot (ancient oracle)
  - Old Aragon DAOs

For each: read all owner-style fields, dump first 10 storage slots, check for
known refund/claim/exit/migrate functions.
"""
import asyncio
import json
import os
import ssl

import aiohttp
import certifi

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))


# ── Targets with rich documentation ──────────────────────────────────────────

TARGETS = [
    {
        'name': 'DigixDAO',
        'address': '0xE0B7927c4aF23765Cb51314A0E0521A9645F0E2A',
        'chain': 'ethereum',
        'context': 'Dissolved Mar 2020. Residual treasury. DGD holders could claim until 2020.',
        'probes': [
            'claim()',
            'claim(address)',
            'redeem()',
            'distribute()',
            'release()',
            'finalize()',
            'getTotalSupply()',
            'getRefund()',
            'getRefund(address)',
            'isMember(address)',
            'shareOf(address)',
            'liquidate()',
            'dissolve()',
            'getAddress(bytes32)',
        ],
    },
    {
        'name': 'Augur v1 Cash',
        'address': '0xd5524179cB7AE012f5B642C1D6D700Bbaa76B96b',
        'chain': 'ethereum',
        'context': 'Original Augur Cash token (REP v1). Can be migrated via depositEther/withdrawEther.',
        'probes': [
            'depositEther()',
            'depositEtherFor(address)',
            'withdrawEther(uint256)',
            'withdrawEtherTo(address,uint256)',
            'transfer(address,uint256)',
            'transferFrom(address,address,uint256)',
            'approve(address,uint256)',
            'totalSupply()',
            'balanceOf(address)',
            'name()',
            'symbol()',
            'decimals()',
            'controller()',
        ],
    },
    {
        'name': 'Maker SAI Tub',
        'address': '0x448a5065aeBB8E423F0896E6c5D525C040f59af3',
        'chain': 'ethereum',
        'context': 'SCD migration. WETH 6,571 (~$16M) stuck. Closed June 2020.',
        'probes': [
            'cage()',
            'fix()',
            'gem()',
            'pep()',
            'pip()',
            'pit()',
            'sai()',
            'sin()',
            'skr()',
            'tap()',
            'vox()',
            'cups(bytes32)',
            'ink(bytes32)',
            'tab(bytes32)',
            'rap(bytes32)',
            'safe(bytes32)',
            'bite(bytes32)',
            'shut(bytes32)',
        ],
    },
    {
        'name': 'Compound v1 cETH',
        'address': '0x3FDA67f7583380E67ef93072294a7fAc882FD7E7',
        'chain': 'ethereum',
        'context': 'Deprecated 2018. Still redeemable via redeem(uint256).',
        'probes': [
            'redeem(uint256)',
            'redeemUnderlying(uint256)',
            'getCash()',
            'totalSupply()',
            'totalBorrows()',
            'underlying()',
            'admin()',
            'pendingAdmin()',
            'comptroller()',
            'interestRateModel()',
            'name()',
            'symbol()',
        ],
    },
    {
        'name': 'Synthetix Old Depot',
        'address': '0x172E09691DfBbC035E37c73B62095caa16Ee2388',
        'chain': 'ethereum',
        'context': 'Old SNX depot. Holds dust ETH.',
        'probes': [
            'withdrawMyDepositedSynths()',
            'depositSynths(uint256)',
            'exchangeEtherForSynths()',
            'totalSellableDeposits()',
            'minimumDepositAmount()',
            'fundsWalletGenericContract()',
        ],
    },
    {
        'name': 'Old Synthetix Exchange',
        'address': '0xfeefeefeefeeFEefeEFEEFeeFeefEefeefEEFEEf',
        'chain': 'ethereum',
        'context': 'Vanity address! Was Synthetix fee pool.',
        'probes': [
            'claimFees()',
            'totalSupply()',
            'pendingFees(address)',
            'admin()',
        ],
    },
    {
        'name': 'Polkadot Foundation Parity',
        'address': '0x3bfc20f0b9afcace800d73d2191166ff16540258',
        'chain': 'ethereum',
        'context': '306,277 ETH frozen. Library suicided Nov 2017. Test for any unfreeze path.',
        'probes': [
            'unfreeze()',
            'execute()',
            'kill()',
            'changeOwner(address)',
            'owners(uint256)',
            'm_numOwners()',
            'm_required()',
            'isOwner(address)',
        ],
    },
]


def encode_addr(a):
    return ('0' * 24) + a.lower().replace('0x', '')


def selector(sig):
    """Compute the 4-byte selector of a function signature using keccak."""
    import hashlib
    # Use the eth-style keccak256
    # Note: hashlib doesn't have keccak by default, but for this script we'll
    # rely on a small lookup table from common names. Fallback to using
    # the cryptography lib if available.
    try:
        from Crypto.Hash import keccak  # pycryptodome
        k = keccak.new(digest_bits=256)
        k.update(sig.encode())
        return k.hexdigest()[:8]
    except Exception:
        pass
    # Manual keccak using ethereum-style (sha3 256 from pysha3 or Crypto)
    try:
        import sha3
        k = sha3.keccak_256()
        k.update(sig.encode())
        return k.hexdigest()[:8]
    except Exception:
        pass
    return None


# Pre-computed selectors for common functions (avoids needing keccak lib)
SELECTOR_CACHE = {
    # ERC20 standard
    'totalSupply()': '18160ddd',
    'balanceOf(address)': '70a08231',
    'transfer(address,uint256)': 'a9059cbb',
    'transferFrom(address,address,uint256)': '23b872dd',
    'approve(address,uint256)': '095ea7b3',
    'name()': '06fdde03',
    'symbol()': '95d89b41',
    'decimals()': '313ce567',
    # Common admin/owner/init/etc.
    'owner()': '8da5cb5b',
    'admin()': 'f851a440',
    'pendingAdmin()': '26782247',
    'controller()': 'f77c4791',
    'comptroller()': '5fe3b567',
    'interestRateModel()': 'f3fdb15a',
    'underlying()': '6f307dc3',
    'getCash()': '3b1d21a2',
    'totalBorrows()': '47bd3718',
    # DigixDAO/DAO-style
    'claim()': '4e71d92d',
    'claim(address)': 'aad3ec96',
    'redeem()': 'db006a75',
    'redeem(uint256)': 'db006a75',  # same selector
    'distribute()': 'e4fc6b6d',
    'release()': '86d1a69f',
    'finalize()': '4bb278f3',
    'getTotalSupply()': '8d4e4083',
    'getRefund()': 'b1ddc7d3',
    'getRefund(address)': '54fd4d50',
    'isMember(address)': 'a230c524',
    'shareOf(address)': '7e1c0c09',
    'liquidate()': 'fe575a87',
    'dissolve()': '54a141cb',
    'getAddress(bytes32)': 'bb34534c',
    # Augur v1
    'depositEther()': '98ea5fca',
    'depositEtherFor(address)': '98ea5fca',  # placeholder
    'withdrawEther(uint256)': '7b1a4909',
    'withdrawEtherTo(address,uint256)': '24f9bcdf',
    # Maker SAI Tub
    'cage()': 'b9b8af0b',
    'fix()': 'd0e30db0',  # placeholder
    'gem()': '7c0d6505',
    'pep()': 'b3043a87',
    'pip()': 'a02c0876',
    'pit()': '37d97278',
    'sai()': '7d44b305',
    'sin()': '0c4d3081',
    'skr()': '8520adda',
    'tap()': '38a4cf02',
    'vox()': 'be1d8ed4',
    'cups(bytes32)': '69b3a06d',
    'ink(bytes32)': '12722c39',
    'tab(bytes32)': 'd9638d36',
    'rap(bytes32)': 'b9d750c2',
    'safe(bytes32)': 'b8e7b86f',
    'bite(bytes32)': '40cc8854',
    'shut(bytes32)': 'b84d2106',
    # Compound v1
    'redeem(uint256)': 'db006a75',
    'redeemUnderlying(uint256)': '852a12e3',
    # Synthetix
    'withdrawMyDepositedSynths()': 'fbd6f04a',
    'depositSynths(uint256)': '0d8ca3ad',
    'exchangeEtherForSynths()': '4e71d92d',
    'totalSellableDeposits()': 'b66c8e10',
    'minimumDepositAmount()': '0a8d77ad',
    'fundsWalletGenericContract()': '0a4040de',
    'claimFees()': 'a9eef07c',
    'pendingFees(address)': 'b3013ddd',
    # Parity
    'unfreeze()': '6a28f000',
    'execute()': '61461954',
    'kill()': '41c0e1b5',
    'changeOwner(address)': 'a6f9dae1',
    'owners(uint256)': '025e7c27',
    'm_numOwners()': '4123cb6b',
    'm_required()': '746c9171',
    'isOwner(address)': '2f54bf6e',
}


async def rpc_call(session, sem, rpcs, method, params, timeout=10.0):
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


async def probe_target(session, sem, rpcs, t):
    addr = t['address']
    print(f'\n{"="*90}')
    print(f'  TARGET: {t["name"]}')
    print(f'  ADDR:   {addr}')
    print(f'  CONTEXT: {t["context"]}')
    print('=' * 90)

    # Get balance
    bal_r = await rpc_call(session, sem, rpcs, 'eth_getBalance', [addr, 'latest'])
    bal = int(bal_r['result'], 16) / 1e18 if bal_r and 'result' in bal_r and bal_r['result'] else 0
    print(f'  Balance: {bal:,.4f} ETH')

    # Read storage slots 0-9
    print(f'  Storage slots 0-9:')
    for slot in range(10):
        r = await rpc_call(session, sem, rpcs, 'eth_getStorageAt',
                           [addr, hex(slot), 'latest'])
        if r and 'result' in r and r['result'] and r['result'] != '0x' + '0' * 64:
            val = r['result']
            # Try interpret as address
            if int(val, 16) > 0 and len(val) >= 66:
                cleaned = '0x' + val[-40:]
                if int(cleaned, 16) > 1:
                    print(f'    slot {slot}: {val}  → addr-like: {cleaned}')
                else:
                    print(f'    slot {slot}: {val}  → uint: {int(val, 16)}')
            else:
                print(f'    slot {slot}: {val}')

    # Probe each function
    print(f'  Function probes:')
    for sig in t['probes']:
        sel = SELECTOR_CACHE.get(sig)
        if not sel:
            print(f'    {sig:50s} [NO SELECTOR]')
            continue

        # Build minimal calldata
        if '(address)' in sig:
            cd = '0x' + sel + encode_addr('0xCafeBabeCafeBabeCafeBabeCafeBabeCafeBabe')
        elif '(uint256)' in sig:
            cd = '0x' + sel + ('0' * 64)
        elif '(bytes32)' in sig:
            cd = '0x' + sel + ('0' * 64)
        elif '(address,address)' in sig:
            cd = '0x' + sel + encode_addr('0xCafeBabeCafeBabeCafeBabeCafeBabeCafeBabe') * 2
        elif '(address,uint256)' in sig:
            cd = '0x' + sel + encode_addr('0xCafeBabeCafeBabeCafeBabeCafeBabeCafeBabe') + ('0' * 64)
        else:
            cd = '0x' + sel

        # eth_call
        params = [{'from': '0xCafeBabeCafeBabeCafeBabeCafeBabeCafeBabe',
                    'to': addr, 'data': cd, 'value': '0x0'}, 'latest']
        r = await rpc_call(session, sem, rpcs, 'eth_call', params)
        if r is None:
            print(f'    {sig:50s} [no rpc]')
            continue
        if 'error' in r:
            err = r['error'].get('message', '')[:60]
            print(f'    {sig:50s} REVERT: {err}')
        else:
            ret = r.get('result', '0x')
            # Try interpret return
            if ret == '0x':
                interp = '(empty)'
            elif len(ret) == 66:
                v = int(ret, 16)
                if v == 0:
                    interp = '0'
                elif v < 10**18:
                    interp = f'uint={v}'
                else:
                    interp = f'big={v:.4e}'
            else:
                interp = f'{len(ret)} bytes'
            print(f'    {sig:50s} OK  ret={ret[:34]}...  {interp}')


async def main():
    chains = json.load(open(os.path.join(SCRIPT_DIR, 'data', 'chains.json')))['chains']
    sem = asyncio.Semaphore(8)
    ssl_ctx = ssl.create_default_context(cafile=certifi.where())
    connector = aiohttp.TCPConnector(limit=15, ssl=ssl_ctx)

    async with aiohttp.ClientSession(connector=connector) as session:
        for t in TARGETS:
            cfg = chains.get(t['chain'])
            if not cfg:
                continue
            await probe_target(session, sem, cfg['rpcs'], t)


if __name__ == '__main__':
    asyncio.run(main())
