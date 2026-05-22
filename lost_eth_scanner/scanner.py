#!/usr/bin/env python3
"""
LOST ETH SCANNER
================
Scan a wallet address against known dormant/forgotten Ethereum contracts.
Reports any recoverable balances (ETH or ERC-20) the address may have stuck.

ETHICAL USE: Only scans balances belonging to the address you provide.
You can WITHDRAW only what is registered to that address (need its private key).

Usage:
    python3 scanner.py 0xYourAddress
    python3 scanner.py 0xAddress1 0xAddress2 0xAddress3
"""

import sys
import os
import json
import requests

RPC_ENDPOINTS = [
    'https://ethereum-rpc.publicnode.com',
    'https://eth.llamarpc.com',
    'https://rpc.ankr.com/eth',
    'https://cloudflare-eth.com',
]

# Common tokens to check on EtherDelta-style DEXs (token contract -> human name + decimals)
COMMON_TOKENS = {
    '0x0000000000000000000000000000000000000000': ('ETH', 18),
    '0x6b175474e89094c44da98b954eedeac495271d0f': ('DAI', 18),
    '0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48': ('USDC', 6),
    '0xdac17f958d2ee523a2206206994597c13d831ec7': ('USDT', 6),
    '0x514910771af9ca656af840dff83e8264ecf986ca': ('LINK', 18),
    '0x744d70fdbe2ba4cf95131626614a1763df805b9e': ('SNT', 18),
    '0xb705268213d593b8fd88d3fdeff93aff5cbdcfae': ('IDEX', 18),
    '0x4f3afec4e5a3f2a6a1a411def7d7dfe50ee057bf': ('DGD', 9),
    '0xf230b790e05390fc8295f4d3f60332c93bed42e2': ('TRX', 6),
    '0x1985365e9f78359a9b6ad760e32412f4a445e862': ('REP', 18),
    '0xe41d2489571d322189246dafa5ebde1f4699f498': ('ZRX', 18),
    '0xd26114cd6ee289accf82350c8d8487fedb8a0c07': ('OMG', 18),
    '0xc011a73ee8576fb46f5e1c5751ca3b9fe0af2a6f': ('SNX', 18),
    '0x4156d3342d5c385a87d264f90653733592000581': ('SALT', 8),
    '0xb97048628db6b661d4c2aa833e95dbe1a905b280': ('PAY', 18),
    '0xa4e8c3ec456107ea67d3075bf9e3df3a75823db0': ('LOOM', 18),
    '0xb63b606ac810a52cca15e44bb630fd42d8d1d83d': ('MCO', 8),
    '0x57ab1ec28d129707052df4df418d58a2d46d5f51': ('sUSD', 18),
    '0xfa1a856cfa3409cfa145fa4e20eb270df3eb21ab': ('IOST', 18),
    '0x0d8775f648430679a709e98d2b0cb6250d2887ef': ('BAT', 18),
    '0x9f8f72aa9304c8b593d555f12ef6589cc3a579a2': ('MKR', 18),
    '0xdd974d5c2e2928dea5f71b9825b8b646686bd200': ('KNC', 18),
    '0xf629cbd94d3791c9250152bd8dfbdf380e2a3b9c': ('ENJ', 18),
    '0x6c6ee5e31d828de241282b9606c8e98ea48526e2': ('HOT', 18),
    '0x42d6622dece394b54999fbd73d108123806f6a18': ('SPANK', 18),
    '0x687bfc3e73f6af55f0ccca8450114d107e781a0e': ('QSP', 18),
    '0x1a7a8bd9106f2b8d977e08582dc7d24c723ab0db': ('AppCoins', 18),
    '0xeb7c20027172e5d143fb030d50f91cece2d1485d': ('eBTC', 8),
}

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
with open(os.path.join(SCRIPT_DIR, 'contracts.json')) as f:
    CONTRACTS_DB = json.load(f)['contracts']


def rpc_call(method, params, retries=2):
    last_err = None
    for rpc in RPC_ENDPOINTS:
        for _ in range(retries):
            try:
                r = requests.post(rpc, json={
                    'jsonrpc': '2.0', 'method': method, 'params': params, 'id': 1
                }, timeout=8)
                d = r.json()
                if 'result' in d:
                    return d['result']
                last_err = d.get('error')
            except Exception as e:
                last_err = str(e)
                continue
    return None


def encode_addr(a):
    return ('0' * 24) + a.lower().replace('0x', '')


def check_eth_balance_in_dex(contract_addr, user_addr):
    """balanceOf(0x0, user) on EtherDelta-style DEX."""
    data = '0xf7888aec' + ('0' * 64) + encode_addr(user_addr)
    res = rpc_call('eth_call', [{'to': contract_addr, 'data': data}, 'latest'])
    if res and res != '0x':
        try:
            return int(res, 16)
        except Exception:
            return 0
    return 0


def check_token_balance_in_dex(contract_addr, token_addr, user_addr):
    """balanceOf(token, user) on EtherDelta-style DEX."""
    data = '0xf7888aec' + encode_addr(token_addr) + encode_addr(user_addr)
    res = rpc_call('eth_call', [{'to': contract_addr, 'data': data}, 'latest'])
    if res and res != '0x':
        try:
            return int(res, 16)
        except Exception:
            return 0
    return 0


def check_native_balance(user_addr):
    res = rpc_call('eth_getBalance', [user_addr, 'latest'])
    return int(res, 16) if res else 0


def get_eth_price():
    try:
        r = requests.get(
            'https://api.coingecko.com/api/v3/simple/price?ids=ethereum&vs_currencies=usd',
            timeout=10
        ).json()
        return r.get('ethereum', {}).get('usd', 0)
    except Exception:
        return 0


def scan_address(user_addr, eth_price=0):
    print(f'\n{"=" * 72}')
    print(f'  Scanning: {user_addr}')
    print(f'{"=" * 72}\n')

    findings = []
    grand_total_eth = 0.0

    direct_eth = check_native_balance(user_addr)
    if direct_eth > 0:
        eth_amt = direct_eth / 1e18
        usd = eth_amt * eth_price if eth_price else 0
        usd_str = f' (~${usd:,.2f})' if usd else ''
        print(f'  [INFO] Wallet native ETH balance: {eth_amt:.6f} ETH{usd_str}')
        print(f'         (this is your direct wallet, not stuck in any contract)')
    print()

    for contract in CONTRACTS_DB:
        if contract.get('_comment'):
            continue
        name = contract['name']
        addr = contract['address']
        ctype = contract.get('type', '')
        is_etherdelta_style = 'EtherDelta' in ctype or contract.get('balance_selector') == '0xf7888aec'

        prefix = f'  [{name[:28]:28s}] {addr[:10]}... '

        if not is_etherdelta_style:
            print(f'{prefix} - skipped (custom check needed)')
            continue

        stuck_eth = check_eth_balance_in_dex(addr, user_addr)
        local_findings = []

        if stuck_eth > 0:
            eth_amt = stuck_eth / 1e18
            usd = eth_amt * eth_price if eth_price else 0
            grand_total_eth += eth_amt
            local_findings.append({
                'contract': name,
                'address': addr,
                'token': 'ETH',
                'token_address': '0x0000000000000000000000000000000000000000',
                'amount': eth_amt,
                'amount_wei': stuck_eth,
                'usd': usd,
                'withdraw_method': contract.get('withdraw_method', 'withdraw(address,uint256)'),
            })

        # Always scan tokens (small list, fast)
        for token_addr, (sym, dec) in COMMON_TOKENS.items():
            if token_addr == '0x0000000000000000000000000000000000000000':
                continue
            bal = check_token_balance_in_dex(addr, token_addr, user_addr)
            if bal > 0:
                amount = bal / (10 ** dec)
                local_findings.append({
                    'contract': name,
                    'address': addr,
                    'token': sym,
                    'token_address': token_addr,
                    'amount': amount,
                    'amount_wei': bal,
                    'withdraw_method': contract.get('withdraw_method', 'withdraw(address,uint256)'),
                })

        if local_findings:
            print(f'{prefix} FOUND {len(local_findings)} balance(s)!')
            for f in local_findings:
                usd_str = f' (~${f.get("usd", 0):,.2f})' if f.get('usd') else ''
                print(f'         -> {f["amount"]:>14,.6f} {f["token"]}{usd_str}')
            findings.extend(local_findings)
        else:
            print(f'{prefix} clean')

    print(f'\n{"-" * 72}')
    print(f'  Summary for {user_addr}')
    print(f'{"-" * 72}')
    if findings:
        print(f'  RECOVERABLE BALANCES FOUND: {len(findings)}')
        print()
        for f in findings:
            usd_str = f' (~${f.get("usd", 0):,.2f})' if f.get('usd') else ''
            print(f'    [{f["contract"]}]')
            print(f'      Token:   {f["token"]} ({f["token_address"]})')
            print(f'      Amount:  {f["amount"]:,.6f}{usd_str}')
            print(f'      Method:  {f["withdraw_method"]}')
            print(f'      Wei:     {f["amount_wei"]}')
            print()
        print(f'  HOW TO WITHDRAW:')
        print(f'  1) Use this address ({user_addr}) - you must control its private key')
        print(f'  2) Run: python3 withdraw_helper.py <contract> <token> <amount_wei>')
        print(f'  3) Sign the transaction with MetaMask/MEW/hardware wallet')
    else:
        print(f'  No stuck balances found in scanned contracts.')
        print(f'  Database checked: {len([c for c in CONTRACTS_DB if not c.get("_comment")])} contracts')

    return findings


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    addresses = sys.argv[1:]
    print('LOST ETH SCANNER')
    print(f'Scanning {len(addresses)} address(es) against {len(CONTRACTS_DB)} dormant contracts')
    print()

    eth_price = get_eth_price()
    print(f'Current ETH price: ${eth_price:,.2f}')

    all_findings = {}
    for addr in addresses:
        addr = addr.lower()
        if not (addr.startswith('0x') and len(addr) == 42):
            print(f'  Skipping invalid address: {addr}')
            continue
        all_findings[addr] = scan_address(addr, eth_price)

    print(f'\n\n{"=" * 72}')
    print('  FINAL REPORT')
    print(f'{"=" * 72}')
    total = sum(len(v) for v in all_findings.values())
    if total == 0:
        print('  No stuck balances found across all scanned addresses.')
        print()
        print('  Suggestions:')
        print('  - If you used DEXs in 2017-2020, try old MetaMask/MEW addresses')
        print('  - Check old hardware wallet derivation paths')
        print('  - Search email for "IDEX", "EtherDelta", "deposit confirmation"')
    else:
        total_eth = sum(
            f.get('amount', 0) for findings in all_findings.values()
            for f in findings if f.get('token') == 'ETH'
        )
        usd_total = total_eth * eth_price if eth_price else 0
        print(f'  Total stuck balances found: {total}')
        print(f'  Total ETH recoverable:      {total_eth:.4f} (~${usd_total:,.2f})')
        print()
        for addr, findings in all_findings.items():
            if findings:
                print(f'  {addr}:')
                for f in findings:
                    print(f'    {f["amount"]:>14,.6f} {f["token"]:8s} in {f["contract"]}')


if __name__ == '__main__':
    main()
