#!/usr/bin/env python3
"""
Deep-dive analyzer for a single contract.
Fetches code, traces what happens when you call key selectors.
"""
import json, sys, os, ssl, urllib.request, certifi


def fetch_code(rpc, addr):
    body = json.dumps({
        'jsonrpc': '2.0', 'method': 'eth_getCode', 'params': [addr, 'latest'], 'id': 1
    }).encode()
    req = urllib.request.Request(rpc, data=body, headers={
        'Content-Type': 'application/json',
        'User-Agent': 'Mozilla/5.0 (compatible; analyzer/1.0)',
    })
    ctx = ssl.create_default_context(cafile=certifi.where())
    with urllib.request.urlopen(req, timeout=15, context=ctx) as resp:
        return json.loads(resp.read()).get('result', '0x')


def fetch_balance(rpc, addr):
    body = json.dumps({
        'jsonrpc': '2.0', 'method': 'eth_getBalance', 'params': [addr, 'latest'], 'id': 1
    }).encode()
    req = urllib.request.Request(rpc, data=body, headers={
        'Content-Type': 'application/json',
        'User-Agent': 'Mozilla/5.0 (compatible; analyzer/1.0)',
    })
    ctx = ssl.create_default_context(cafile=certifi.where())
    with urllib.request.urlopen(req, timeout=15, context=ctx) as resp:
        r = json.loads(resp.read()).get('result', '0x0')
        return int(r, 16)


def call_contract(rpc, addr, sender, calldata):
    body = json.dumps({
        'jsonrpc': '2.0', 'method': 'eth_call',
        'params': [{'from': sender, 'to': addr, 'data': calldata, 'value': '0x0'}, 'latest'],
        'id': 1
    }).encode()
    req = urllib.request.Request(rpc, data=body, headers={
        'Content-Type': 'application/json',
        'User-Agent': 'Mozilla/5.0 (compatible; analyzer/1.0)',
    })
    ctx = ssl.create_default_context(cafile=certifi.where())
    try:
        with urllib.request.urlopen(req, timeout=15, context=ctx) as resp:
            return json.loads(resp.read())
    except Exception as e:
        return {'error': str(e)}


def get_owner_etc(rpc, addr):
    """Try standard owner functions."""
    out = {}
    sels = {
        '8da5cb5b': 'owner()',
        '893d20e8': 'getOwner()',
        'f851a440': 'admin()',
        '06fdde03': 'name()',
        '95d89b41': 'symbol()',
    }
    for sel, name in sels.items():
        r = call_contract(rpc, addr, '0x0000000000000000000000000000000000000000', '0x' + sel)
        if 'result' in r and r['result'] != '0x':
            out[name] = r['result']
    return out


# Targets to investigate
TARGETS = [
    ('zksync',    '0x8B791913eB07C32779a16750e3868aA8495F5964', 'Mute.io Router'),
    ('ethereum',  '0x1A2a1c938CE3eC39b6D47113c7955bAa9DD454F2', 'Ronin Bridge (old)'),
    ('moonbeam',  '0x96b244391D98B62D19aE89b1A4dCcf0fc56970C7', 'Beamswap'),
    ('zksync',    '0x39E098A153Ad69834a9Dac32f0FCa92066aD03f4', 'Maverick zkSync'),
    ('celo',      '0xE3D8bd6Aed4F159bc8000a9cD47CffDb95F96121', 'Ubeswap V1'),
    ('linea',     '0x1d0188c4B276A09366D05d6Be06aF61a73bC7535', 'Velocore'),
    ('arbitrum',  '0xC4ABADE3a15064F9E3596943c699032748b13352', 'Vela Exchange'),
]


def main():
    chains = json.load(open(os.path.join(os.path.dirname(__file__), 'data', 'chains.json')))['chains']
    for chain, addr, name in TARGETS:
        rpc = chains[chain]['rpcs'][0]
        print(f'\n{"="*80}\n  {chain.upper()}  {name}\n  {addr}\n{"="*80}')
        try:
            bal = fetch_balance(rpc, addr)
            print(f'  Balance: {bal/1e18:,.4f} native')
            code = fetch_code(rpc, addr)
            print(f'  Code size: {(len(code)-2)//2} bytes')
            if not code or code == '0x':
                print(f'  -> EOA, skip')
                continue
            meta = get_owner_etc(rpc, addr)
            for k, v in meta.items():
                if v.startswith('0x') and len(v) >= 66:
                    if k.endswith('()') and 'name' not in k and 'symbol' not in k:
                        # address
                        print(f'  {k:15s} -> 0x{v[-40:]}')
                    else:
                        # try string decode
                        try:
                            raw = bytes.fromhex(v[2:])
                            s = raw.split(b'\x00', 1)[0].decode('utf-8', errors='replace')
                            print(f'  {k:15s} -> {s!r} (raw: {v[:50]}...)')
                        except:
                            print(f'  {k:15s} -> {v[:80]}')
        except Exception as e:
            print(f'  ERROR: {e}')


if __name__ == '__main__':
    main()
