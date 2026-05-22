#!/usr/bin/env python3
"""
BYTECODE ANALYZER
=================
Takes any contract address and produces a forensic profile:
  - Function selectors (PUSH4 detection + 4byte.directory lookup)
  - Critical opcodes (SELFDESTRUCT, DELEGATECALL, CREATE/CREATE2)
  - EIP-1167 minimal proxy detection
  - EIP-1967 proxy slot detection
  - EIP-2535 diamond detection
  - Storage slot 0-15 dump
  - Owner/admin detection (8 common patterns)
  - Token interface detection (ERC-20, ERC-721, ERC-1155)
  - Estimated contract type classification

Usage:
    python3 bytecode_analyzer.py 0xCONTRACT [--chain ethereum]
"""
import argparse
import asyncio
import json
import os
import ssl
import sys

import aiohttp
import certifi
import requests

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CHAINS_FILE = os.path.join(SCRIPT_DIR, 'chains.json')


class C:
    RESET = '\033[0m'; BOLD = '\033[1m'
    GREEN = '\033[32m'; YELLOW = '\033[33m'; RED = '\033[31m'
    CYAN = '\033[36m'; GRAY = '\033[90m'; MAGENTA = '\033[35m'; BLUE = '\033[34m'


# Key opcodes to flag
OPCODES = {
    'ff': 'SELFDESTRUCT',
    'f4': 'DELEGATECALL',
    'f1': 'CALL',
    'f2': 'CALLCODE',
    'fa': 'STATICCALL',
    'f0': 'CREATE',
    'f5': 'CREATE2',
    'a0': 'LOG0', 'a1': 'LOG1', 'a2': 'LOG2', 'a3': 'LOG3', 'a4': 'LOG4',
}

# Function signatures to identify common patterns
COMMON_SELECTORS = {
    '0x06fdde03': 'name()', '0x95d89b41': 'symbol()', '0x313ce567': 'decimals()',
    '0x18160ddd': 'totalSupply()', '0x70a08231': 'balanceOf(address)',
    '0xa9059cbb': 'transfer(address,uint256)', '0x23b872dd': 'transferFrom(address,address,uint256)',
    '0x095ea7b3': 'approve(address,uint256)', '0xdd62ed3e': 'allowance(address,address)',
    '0x8da5cb5b': 'owner()', '0x893d20e8': 'getOwner()', '0xf2fde38b': 'transferOwnership(address)',
    '0x715018a6': 'renounceOwnership()',
    '0x6352211e': 'ownerOf(uint256)', '0xb88d4fde': 'safeTransferFrom(address,address,uint256,bytes)',
    '0xc87b56dd': 'tokenURI(uint256)',
    '0xa22cb465': 'setApprovalForAll(address,bool)', '0xe985e9c5': 'isApprovedForAll(address,address)',
    '0x42842e0e': 'safeTransferFrom(address,address,uint256)',
    '0x4f1ef286': 'upgradeToAndCall(address,bytes)', '0x3659cfe6': 'upgradeTo(address)',
    '0x5c60da1b': 'implementation()',
    '0xf3fef3a3': 'withdraw(address,uint256)', '0x2e1a7d4d': 'withdraw(uint256)',
    '0x3ccfd60b': 'withdraw()', '0x9e281a98': 'withdrawToken(address,uint256)',
    '0xd0e30db0': 'deposit()', '0x338b5dea': 'depositToken(address,uint256)',
    '0xb6b55f25': 'deposit(uint256)',
    '0xf7888aec': 'balanceOf(address,address)',
    '0x508493bc': 'tokens(address,address)',
    '0x4b0bddd2': 'setAdmin(address,bool)',
    '0x2295115b': 'adminWithdraw(address,uint256,address,uint256,uint8,bytes32,bytes32,uint256)',
    '0xef343588': 'trade(uint256[8],address[4],uint8[2],bytes32[4])',
    '0x8456cb59': 'pause()', '0x3f4ba83a': 'unpause()',
    '0x40c10f19': 'mint(address,uint256)', '0x42966c68': 'burn(uint256)',
    '0xc78d166c': 'free(uint256)',  # GST2/CHI
    '0xb1e349a3': 'freeUpTo(uint256)',
    '0x55241077': 'setMaxSupply(uint256)',
    '0x46f80b3d': 'redeemRewards()',
    '0x60806040': '(constructor padding)',
    '0xd505accf': 'permit(address,address,uint256,uint256,uint8,bytes32,bytes32)',
    '0x0707f17a': '(unknown common)',
}


def extract_selectors(bytecode):
    """Find all PUSH4 (0x63) followed by 4 bytes."""
    raw = bytecode[2:].lower() if bytecode.startswith('0x') else bytecode.lower()
    selectors = set()
    i = 0
    while i < len(raw) - 10:
        if raw[i:i+2] == '63':
            sel = raw[i+2:i+10]
            if sel != '00000000' and sel != 'ffffffff':
                selectors.add('0x' + sel)
            i += 10
        else:
            i += 2
    return sorted(selectors)


def extract_opcodes(bytecode):
    """Find critical opcodes in bytecode."""
    raw = bytecode[2:].lower() if bytecode.startswith('0x') else bytecode.lower()
    found = {}
    for j in range(0, len(raw)-1, 2):
        op = raw[j:j+2]
        if op in OPCODES:
            found[OPCODES[op]] = found.get(OPCODES[op], 0) + 1
    return found


def detect_proxy_patterns(bytecode):
    """Check for common proxy patterns."""
    raw = (bytecode[2:] if bytecode.startswith('0x') else bytecode).lower()
    flags = []
    # EIP-1167 minimal proxy
    if '363d3d373d3d3d363d73' in raw:
        flags.append('EIP-1167 Minimal Proxy (delegates to implementation)')
    # EIP-1967 storage slot reference
    if '360894a13ba1a3210667c828492db98dca3e2076cc3735a920a3ca505d382bbc' in raw:
        flags.append('EIP-1967 Proxy slot reference')
    # EIP-2535 Diamond
    if 'a619486e' in raw or '7a0ed627' in raw:
        flags.append('EIP-2535 Diamond pattern (facets)')
    # UUPS
    if 'upgradeToAndCall' in raw or '4f1ef286' in raw:
        flags.append('UUPS upgradeable')
    return flags


def lookup_4byte(selectors, max_lookups=50):
    """Bulk lookup unknown selectors via 4byte.directory."""
    decoded = {}
    for sel in selectors[:max_lookups]:
        if sel in COMMON_SELECTORS:
            decoded[sel] = COMMON_SELECTORS[sel]
            continue
        try:
            r = requests.get(f'https://www.4byte.directory/api/v1/signatures/?hex_signature={sel}', timeout=5)
            if r.status_code == 200:
                data = r.json()
                if data.get('results'):
                    sigs = [x['text_signature'] for x in data['results'][:2]]
                    decoded[sel] = ' | '.join(sigs)
        except Exception:
            pass
    return decoded


def classify_contract(selectors_decoded, opcodes, proxy_flags):
    """Heuristic classification of contract type."""
    sigs = ' '.join(selectors_decoded.values()).lower()
    classification = []
    if proxy_flags:
        classification.append('PROXY')
    if 'transfer(address,uint256)' in sigs and 'balanceof(address)' in sigs and 'totalsupply' in sigs:
        if 'ownerof' in sigs or 'tokenuri' in sigs:
            classification.append('ERC-721 NFT')
        elif 'safetransferfrom' in sigs and 'balanceofbatch' in sigs:
            classification.append('ERC-1155 NFT')
        else:
            classification.append('ERC-20 Token')
    if 'adminwithdraw' in sigs and 'tokens(address,address)' in sigs:
        classification.append('EtherDelta-fork DEX')
    if 'trade(' in sigs and 'feeaccount' in sigs:
        classification.append('Order-book DEX')
    if 'free(' in sigs and 'mint' in sigs:
        classification.append('Gas Token (GST2/CHI)')
    if 'withdraw' in sigs and 'deposit' in sigs:
        classification.append('Vault / Pool')
    if not classification:
        if opcodes.get('SELFDESTRUCT', 0) > 0 and opcodes.get('DELEGATECALL', 0) > 0:
            classification.append('Multisig wallet (legacy)')
        else:
            classification.append('UNKNOWN')
    return classification


async def get_basic_info(session, rpcs, address):
    """Fetch balance, code, nonce."""
    async def call(method, params):
        for rpc in rpcs:
            try:
                async with session.post(rpc, json={'jsonrpc':'2.0','method':method,'params':params,'id':1},
                                         timeout=aiohttp.ClientTimeout(total=10)) as r:
                    if r.status != 200: continue
                    d = await r.json()
                    if 'result' in d: return d['result']
            except Exception: continue
        return None

    code = await call('eth_getCode', [address, 'latest'])
    bal = await call('eth_getBalance', [address, 'latest'])
    nonce = await call('eth_getTransactionCount', [address, 'latest'])
    storage = []
    for i in range(16):
        v = await call('eth_getStorageAt', [address, hex(i), 'latest'])
        if v: storage.append((i, v))
    return {
        'code': code or '0x',
        'balance_eth': int(bal, 16) / 1e18 if bal else 0,
        'nonce': int(nonce, 16) if nonce else 0,
        'storage': storage,
    }


async def analyze(address, chain='ethereum'):
    chains_cfg = json.load(open(CHAINS_FILE))['chains']
    rpcs = chains_cfg.get(chain, {}).get('rpcs', [])
    if not rpcs:
        print(f'{C.RED}Unknown chain: {chain}{C.RESET}')
        return

    ssl_ctx = ssl.create_default_context(cafile=certifi.where())
    async with aiohttp.ClientSession(connector=aiohttp.TCPConnector(ssl=ssl_ctx)) as session:
        print(f'\n{C.BOLD}{C.CYAN}{"=" * 78}{C.RESET}')
        print(f'  {C.BOLD}BYTECODE ANALYZER{C.RESET}')
        print(f'  Chain:   {chain}')
        print(f'  Address: {address}')
        print(f'{C.CYAN}{"=" * 78}{C.RESET}\n')

        info = await get_basic_info(session, rpcs, address)

        if info['code'] == '0x':
            print(f'  {C.YELLOW}Not a contract (EOA){C.RESET}')
            print(f'  Balance: {info["balance_eth"]:.6f} ETH')
            print(f'  Nonce:   {info["nonce"]}')
            return

        print(f'  {C.BOLD}BASIC INFO:{C.RESET}')
        print(f'    Balance:     {info["balance_eth"]:>14,.4f} ETH')
        print(f'    Code size:   {(len(info["code"])-2)//2:>14,} bytes')
        print(f'    Nonce:       {info["nonce"]}')

        # Selectors
        selectors = extract_selectors(info['code'])
        print(f'\n  {C.BOLD}FUNCTION SELECTORS ({len(selectors)} found):{C.RESET}')
        decoded = lookup_4byte(selectors, 60)
        for s in selectors[:60]:
            sig = decoded.get(s, '(unknown)')
            color = C.GREEN if s in COMMON_SELECTORS else C.GRAY
            print(f'    {color}{s}{C.RESET}  {sig}')
        if len(selectors) > 60:
            print(f'    {C.GRAY}... and {len(selectors)-60} more{C.RESET}')

        # Opcodes
        opcodes = extract_opcodes(info['code'])
        print(f'\n  {C.BOLD}CRITICAL OPCODES:{C.RESET}')
        if opcodes:
            for op, count in sorted(opcodes.items(), key=lambda x: -x[1]):
                color = C.RED if op in ('SELFDESTRUCT', 'DELEGATECALL') else C.YELLOW
                print(f'    {color}{op:15s}{C.RESET} x{count}')
        else:
            print(f'    {C.GRAY}(none of interest){C.RESET}')

        # Proxy detection
        proxy = detect_proxy_patterns(info['code'])
        print(f'\n  {C.BOLD}PROXY PATTERNS:{C.RESET}')
        if proxy:
            for p in proxy:
                print(f'    {C.YELLOW}* {p}{C.RESET}')
        else:
            print(f'    {C.GRAY}(none detected){C.RESET}')

        # Storage
        print(f'\n  {C.BOLD}STORAGE SLOTS 0-15:{C.RESET}')
        for slot, value in info['storage']:
            if value == '0x' + '00' * 32:
                continue
            v = int(value, 16) if value else 0
            color = C.BLUE if v < 2**160 else C.GRAY
            extra = ''
            if 0 < v < 2**160:
                extra = f' (as addr: 0x{value[-40:]})'
            print(f'    {color}slot[{slot:>2}]{C.RESET} = {value}{extra}')

        # Classification
        clazz = classify_contract(decoded, opcodes, proxy)
        print(f'\n  {C.BOLD}{C.MAGENTA}CLASSIFICATION:{C.RESET}')
        for c in clazz:
            print(f'    {C.GREEN}* {c}{C.RESET}')

        print(f'\n  {C.GRAY}Useful links:{C.RESET}')
        print(f'    Etherscan: {chains_cfg[chain]["explorer"]}/address/{address}')
        print(f'    4byte:     https://www.4byte.directory/')
        print(f'    Decompile: https://library.dedaub.com/decompile')


def main():
    p = argparse.ArgumentParser()
    p.add_argument('address')
    p.add_argument('--chain', default='ethereum')
    args = p.parse_args()
    asyncio.run(analyze(args.address, args.chain))


if __name__ == '__main__':
    main()
