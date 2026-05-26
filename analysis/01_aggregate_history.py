#!/usr/bin/env python3
"""
20 Forgotten Contracts Scanner
================================
Auto-scans the 20 forgotten contracts identified with confirmed ETH balances.
Reports recoverability analysis per contract.

Usage:
    python3 01_aggregate_history.py
"""
import urllib.request, ssl, json, time
try:
    import certifi
    ctx = ssl.create_default_context(cafile=certifi.where())
except ImportError:
    ctx = ssl.create_default_context()

CONTRACTS = [
    ("0x9a2d163ab40f88c625fd475e807bbc3556566f80", "SingularX", "DEX_OLD"),
    ("0x35fFd6E268610E764fF6944d07760D0EFe5E40E5", "KeeperDAO/Rook", "DEFI_OLD"),
    ("0x220a9f0dd581cbc58fcfb907de0454cbf3777f76", "MCDEX Perp", "PERP_DEX_OLD"),
    ("0xECF8F87f810EcF450940c9f60066b4a7a501d6A7", "Old WETH", "WRAPPED_OLD"),
    ("0x27321f84704a599ab740281e285cc4463d89a3d5", "Keep Network", "STAKING_OLD"),
    ("0x3b960e47784150f5a63777201ee2b15253d713e8", "Opyn Crab V2", "OPTIONS_OLD"),
    ("0x44e081cac2406a4efe165178c2a4d77f7a7854d4", "Celer EthPool", "BRIDGE_OLD"),
    ("0xa383c8390adbcd387db93babdf3f30308391bd57", "ETH Staking Rewards", "STAKING_OLD"),
    ("0x77607588222e01bf892a29Abab45796A2047fc7b", "Unagii Vault", "VAULT_OLD"),
    ("0x04f062809b244e37e7fdc21d9409469c989c2342", "Joyso DEX", "DEX_OLD"),
    ("0xbeeb655808e3bdb83b6998f09dfe1e0f2c66a9be", "SwissCrypto", "DEX_OLD"),
    ("0x2f23228b905ceb4734eb42d9b42805296667c93b", "Coinchangex", "DEX_OLD"),
    ("0xbf29685856fae1e228878dfb35b280c0adcc3b05", "Decentrex", "DEX_OLD"),
    ("0xB3775fB83F7D12A36E0475aBdD1FCA35c091efBe", "PoWH3D", "PYRAMID"),
    ("0xA62142888ABa8370742bE823c1782D17A0389Da1", "Fomo3D Long", "PYRAMID"),
    ("0x167cB3F2446F829eb327344b66E271D1a7eFeC9A", "GandhiJi", "PYRAMID"),
    ("0x52083b1a21a5abc422b1b0bce5c43ca86ef74cd1", "Fomo3D Short", "PYRAMID"),
    ("0x4e8ecf79ade5e2c49b9e30d795517a81e0bf00b8", "Fomo3D Quick", "PYRAMID"),
    ("0x6db943251e4126f913e9733821031791e75df713", "ReadyPlayerONE", "PYRAMID"),
    ("0xfcd3a0f5f416e407647a7518b90354946d316059", "BitConnect Token", "TOKEN_OLD"),
]


def rpc(method, params, url='https://ethereum-rpc.publicnode.com'):
    body = json.dumps({'jsonrpc':'2.0','method':method,'params':params,'id':1}).encode()
    req = urllib.request.Request(url, data=body, headers={
        'Content-Type':'application/json','User-Agent':'Mozilla/5.0'
    })
    with urllib.request.urlopen(req, timeout=15, context=ctx) as resp:
        return json.loads(resp.read())


def main():
    print(f'\n{"="*90}')
    print(f'  20 Forgotten Contracts — Quick Status Check')
    print(f'{"="*90}')
    
    total = 0
    for addr, name, cat in CONTRACTS:
        try:
            r = rpc('eth_getBalance', [addr, 'latest'])
            bal = int(r['result'], 16) / 1e18 if r and 'result' in r else 0
            total += bal
            print(f'  {name:25s} {bal:>10,.4f} ETH  ({cat})')
        except Exception as e:
            print(f'  {name}: ERROR {e}')
    
    print(f'\n  TOTAL: {total:,.4f} ETH (~${total*2500:,.0f})')


if __name__ == '__main__':
    main()
