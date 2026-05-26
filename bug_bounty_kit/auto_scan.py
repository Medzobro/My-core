#!/usr/bin/env python3
"""
Auto Bug Scanner — Quick triage of smart contracts for common vulnerabilities.

Repurposes infrastructure from lost_eth_scanner for legitimate bug hunting.

Usage:
    python3 auto_scan.py 0xContractAddress           # ethereum
    python3 auto_scan.py 0xContract chainName        # other chain
    python3 auto_scan.py --file addresses.txt        # batch
"""
import argparse
import asyncio
import json
import os
import ssl
import sys
import urllib.request

try:
    import certifi
    _SSL_CTX = ssl.create_default_context(cafile=certifi.where())
except ImportError:
    _SSL_CTX = ssl.create_default_context()

CHAINS = {
    'ethereum': 'https://ethereum-rpc.publicnode.com',
    'arbitrum': 'https://arbitrum-one-rpc.publicnode.com',
    'optimism': 'https://optimism-rpc.publicnode.com',
    'base': 'https://base-rpc.publicnode.com',
    'polygon': 'https://polygon-bor-rpc.publicnode.com',
    'bsc': 'https://bsc-rpc.publicnode.com',
}

# Known dangerous selectors that may indicate vulnerable patterns
DANGEROUS_SELECTORS = {
    # Self-destruct
    '41c0e1b5': ('kill()', 'CRITICAL if not access-controlled'),
    '35f46994': ('destroy()', 'CRITICAL if public'),
    '9cb8a26a': ('destruct()', 'CRITICAL if public'),
    # Initialization
    '8129fc1c': ('initialize()', 'CRITICAL if uninitialized + callable'),
    '4cd88b76': ('init()', 'CRITICAL if uninitialized + callable'),
    'c4d66de8': ('initialize(address)', 'CRITICAL if uninitialized'),
    # Forwarder/execute patterns (suspicious)
    'fc6f7865': ('execute(address,uint,bytes)', 'HIGH if not auth-gated'),
    'b61d27f6': ('execute(address,uint,bytes)', 'HIGH if not auth-gated'),
    # Owner/admin transfer
    'a6f9dae1': ('changeOwner(address)', 'CRITICAL if not access-controlled'),
    'f2fde38b': ('transferOwnership(address)', 'OK if onlyOwner'),
    # Withdraw without state check
    '3ccfd60b': ('withdraw()', 'review for access control'),
    'a64f0bb9': ('recoverETH()', 'review for access control'),
    'b95459e4': ('rescueETH()', 'review for access control'),
}

OPCODE_RISKS = {
    0xff: ('SELFDESTRUCT', 'CRITICAL — contract can self-destruct'),
    0xf4: ('DELEGATECALL', 'HIGH — proxy/library risk'),
    0xf2: ('CALLCODE', 'HIGH — deprecated, like delegatecall'),
    0x32: ('ORIGIN', 'MEDIUM — tx.origin = phishing risk'),
}


def rpc(method, params, rpc_url, timeout=15):
    body = json.dumps({'jsonrpc':'2.0','method':method,'params':params,'id':1}).encode()
    req = urllib.request.Request(rpc_url, data=body, headers={
        'Content-Type':'application/json','User-Agent':'Mozilla/5.0',
    })
    with urllib.request.urlopen(req, timeout=timeout, context=_SSL_CTX) as resp:
        return json.loads(resp.read())


def find_selectors(code_hex):
    if not code_hex or code_hex == '0x':
        return set()
    raw = code_hex[2:].lower()
    sels = set()
    i = 0
    while i < len(raw) - 10:
        if raw[i:i+2] == '63':
            s = raw[i+2:i+10]
            if s != '00000000' and s != 'ffffffff':
                sels.add(s)
            i += 10
        else:
            i += 2
    return sels


def find_opcodes(code_hex):
    if not code_hex or code_hex == '0x':
        return set()
    raw = bytes.fromhex(code_hex[2:])
    ops = set()
    i = 0
    while i < len(raw):
        op = raw[i]
        if 0x60 <= op <= 0x7f:
            i += 1 + (op - 0x5f)
        else:
            ops.add(op)
            i += 1
    return ops


def analyze(addr, rpc_url):
    print(f'\n{"="*70}')
    print(f'  ANALYSIS: {addr}')
    print(f'{"="*70}')

    code_r = rpc('eth_getCode', [addr, 'latest'], rpc_url)
    code = code_r.get('result', '0x')
    if code == '0x':
        print(f'  EOA - skipping')
        return None
    code_size = (len(code) - 2) // 2
    print(f'  Code size: {code_size:,} bytes')

    bal_r = rpc('eth_getBalance', [addr, 'latest'], rpc_url)
    bal = int(bal_r.get('result', '0x0'), 16) / 1e18
    print(f'  Balance:   {bal:,.4f} ETH (${bal*2500:,.0f})')

    # Check selectors
    sels = find_selectors(code)
    print(f'\n  📋 Selectors: {len(sels)} found')
    risks_found = []
    for s in sorted(sels):
        if s in DANGEROUS_SELECTORS:
            name, risk = DANGEROUS_SELECTORS[s]
            print(f'    ⚠️  {s}: {name} - {risk}')
            risks_found.append({'sel': s, 'name': name, 'risk': risk})

    # Check dangerous opcodes
    print(f'\n  🔧 Opcode analysis:')
    ops = find_opcodes(code)
    for op_byte, (name, risk) in OPCODE_RISKS.items():
        if op_byte in ops:
            print(f'    ⚠️  {name} (0x{op_byte:02x}): {risk}')

    # Check EIP-1967 proxy slots
    print(f'\n  🔍 Proxy detection (EIP-1967):')
    EIP1967_IMPL = '0x360894a13ba1a3210667c828492db98dca3e2076cc3735a920a3ca505d382bbc'
    EIP1967_ADMIN = '0xb53127684a568b3173ae13b9f8a6016e243e63b6e8ee1178d6a717850b5d6103'

    impl_r = rpc('eth_getStorageAt', [addr, EIP1967_IMPL, 'latest'], rpc_url)
    if impl_r.get('result') and impl_r['result'] != '0x' + '0'*64:
        impl_addr = '0x' + impl_r['result'][-40:]
        print(f'    Implementation: {impl_addr}')

    admin_r = rpc('eth_getStorageAt', [addr, EIP1967_ADMIN, 'latest'], rpc_url)
    if admin_r.get('result') and admin_r['result'] != '0x' + '0'*64:
        admin_addr = '0x' + admin_r['result'][-40:]
        print(f'    Admin:          {admin_addr}')

    # Try to fetch verified source
    print(f'\n  📚 Sourcify check:')
    try:
        url = f'https://sourcify.dev/server/files/any/1/{addr}'
        req = urllib.request.Request(url, headers={'User-Agent':'Mozilla/5.0','Accept':'application/json'})
        with urllib.request.urlopen(req, timeout=10, context=_SSL_CTX) as resp:
            data = json.loads(resp.read())
            if 'files' in data:
                print(f'    ✅ Verified! {len(data["files"])} files')
                for f in data['files']:
                    if isinstance(f, dict) and f.get('name', '').endswith('.sol'):
                        print(f'    📄 {f["name"]}')
            else:
                print(f'    ❌ Not on Sourcify')
    except Exception as e:
        print(f'    ⚠️  Sourcify error: {e}')

    return {
        'address': addr,
        'code_size': code_size,
        'balance': bal,
        'risks': risks_found,
    }


def main():
    if len(sys.argv) < 2:
        print('Usage: python3 auto_scan.py 0xContract [chain]')
        return

    addr = sys.argv[1]
    chain = sys.argv[2] if len(sys.argv) > 2 else 'ethereum'
    if chain not in CHAINS:
        print(f'Unknown chain. Available: {list(CHAINS.keys())}')
        return

    rpc_url = CHAINS[chain]
    print(f'  Scanning {addr} on {chain}...')
    analyze(addr, rpc_url)

    print(f'\n{"="*70}')
    print(f'  ✅ Scan complete')
    print(f'  Next steps:')
    print(f'    1. Fetch verified source from Etherscan/Sourcify')
    print(f'    2. Review functions with risk flags above')
    print(f'    3. Run Slither: slither {addr} --etherscan-apikey YOUR_KEY')
    print(f'    4. Write Foundry test to confirm vulnerability')
    print(f'    5. If confirmed, submit to Immunefi/Code4rena')


if __name__ == '__main__':
    main()
