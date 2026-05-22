#!/usr/bin/env python3
"""
HD WALLET SCANNER
=================
Given a 12/24-word BIP-39 mnemonic OR a master public key OR a list of
private keys, derive addresses across common derivation paths and check
each one for unclaimed funds in the abandoned-DEX contracts.

Common paths to check:
  - m/44'/60'/0'/0/{0..50}    standard (MetaMask, MyEtherWallet, Trezor)
  - m/44'/60'/0'/{0..5}        Ledger Live early
  - m/44'/60'/{0..5}'/0/0      Ledger Legacy
  - m/0'/0/{0..10}             very old wallets (2014-2016 Mist)

⚠️ SECURITY: Run this OFFLINE on an air-gapped machine if your seed has value.
   The seed phrase is loaded into memory; if your machine is compromised, you lose everything.

Dependencies (only loaded when --mnemonic is used):
  pip install eth-account==0.13.* mnemonic
"""
import asyncio, json, os, ssl, sys, argparse
import aiohttp, certifi

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))


# Common derivation paths to scan
DEFAULT_PATHS = [
    # MetaMask / MEW / Trezor / standard
    "m/44'/60'/0'/0/{i}",
    # Ledger Live
    "m/44'/60'/{i}'/0/0",
    # Ledger Legacy
    "m/44'/60'/0'/{i}",
    # Very old (Mist)
    "m/0'/0/{i}",
]


# Same checks as check_my_addresses.py
CHECKS = [
    ('EtherDelta v1', '0x8da0d80f5007ef1e431dd2127178d224e32c2ef4', '0xf7888aec', 'token_user'),
    ('EtherDelta v2', '0x4aBB0f5fd529cD8C3F80FB6C2e5249084B7CfA63', '0xf7888aec', 'token_user'),
    ('ForkDelta v3',  '0x8d12A197cB00D4747a1fe03395095ce2A5CC6819', '0xf7888aec', 'token_user'),
    ('IDEX 1.0',      '0x2a0c0DBEcC7E4D658f48E01e3fA353F44050c208', '0xf7888aec', 'token_user'),
    ('Token.Store',   '0x1ce7AE555139c5EF5A57CC8d814a867ee6Ee33D8', '0xf7888aec', 'token_user'),
    ('CryptoPunks V2 pendingWithdrawals', '0xb47e3cd837dDF8e4c57F05d70Ab865de6e193BBB', '0xf3f43703', 'user'),
    ('CryptoPunks V1 pendingWithdrawals', '0x6BA6f2207e343923BA692e5Cae646Fb0F566DB8D', '0xf3f43703', 'user'),
    ('Compound v1 cETH balance',          '0x3FDA67f7583380E67ef93072294a7fAc882FD7E7', '0x70a08231', 'user'),
    ('WithdrawDAO eligibility (DAO)',     '0xbb9bc244d798123fde783fcc1c72d3bb8c189413', '0x70a08231', 'user'),
]


def encode_addr(a):
    return ('0' * 24) + a.lower().replace('0x', '')


async def rpc_call(session, sem, rpcs, method, params, timeout=10.0):
    payload = {'jsonrpc': '2.0', 'method': method, 'params': params, 'id': 1}
    async with sem:
        for url in rpcs:
            try:
                async with session.post(url, json=payload,
                                        timeout=aiohttp.ClientTimeout(total=timeout)) as resp:
                    if resp.status != 200:
                        continue
                    data = await resp.json()
                    if 'result' in data:
                        return data['result']
            except Exception:
                continue
    return None


async def check_one(session, sem, rpcs, contract, user, sel, arg_template):
    if arg_template == 'token_user':
        data = sel + encode_addr('0x0000000000000000000000000000000000000000') + encode_addr(user)
    else:
        data = sel + encode_addr(user)
    r = await rpc_call(session, sem, rpcs, 'eth_call',
                       [{'to': contract, 'data': data}, 'latest'])
    if r and r != '0x':
        try: return int(r, 16)
        except: return 0
    return 0


async def check_native_balance(session, sem, rpcs, addr):
    r = await rpc_call(session, sem, rpcs, 'eth_getBalance', [addr, 'latest'])
    return int(r, 16) if r else 0


def derive_addresses(mnemonic, n_per_path=20):
    """Derive Ethereum addresses for the given BIP-39 mnemonic."""
    try:
        from eth_account import Account
        from mnemonic import Mnemonic
    except ImportError:
        print('Run: pip install eth-account mnemonic')
        sys.exit(1)

    Account.enable_unaudited_hdwallet_features()
    out = []
    for path_template in DEFAULT_PATHS:
        for i in range(n_per_path):
            path = path_template.format(i=i)
            try:
                acct = Account.from_mnemonic(mnemonic, account_path=path)
                out.append((path, acct.address))
            except Exception as e:
                # some paths might not be supported
                pass
    return out


async def scan_addresses(session, sem, rpcs, addr_list):
    found = []
    for path, addr in addr_list:
        # Native balance
        nb = await check_native_balance(session, sem, rpcs, addr)
        if nb > 0:
            print(f'  ★ {path:35s} {addr}  NATIVE: {nb/1e18:,.6f} ETH')
            found.append({'path': path, 'addr': addr, 'check': 'native', 'eth': nb/1e18})

        # DEX checks
        for name, contract, sel, arg in CHECKS:
            bal = await check_one(session, sem, rpcs, contract, addr, sel, arg)
            if bal > 0:
                # Decimals: 8 for cETH, 16 for DAO, 18 default
                dec = 18
                if 'Compound' in name: dec = 8
                elif 'WithdrawDAO' in name: dec = 16
                val = bal / (10 ** dec)
                print(f'  ★★ {path:35s} {addr}  {name}: {val:,.6f}')
                found.append({'path': path, 'addr': addr, 'check': name, 'value': val})
    return found


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--mnemonic', help='BIP-39 mnemonic phrase (12 or 24 words)')
    p.add_argument('--mnemonic-file', help='Path to file containing the mnemonic')
    p.add_argument('--addresses-file', help='File with list of addresses to scan (one per line)')
    p.add_argument('--n', type=int, default=20, help='Number of addresses to derive per path (default 20)')
    args = p.parse_args()

    if args.mnemonic_file:
        with open(args.mnemonic_file) as f:
            args.mnemonic = f.read().strip()

    addresses = []
    if args.mnemonic:
        print(f'[*] Deriving {args.n} addresses for each of {len(DEFAULT_PATHS)} paths...')
        addresses = derive_addresses(args.mnemonic, args.n)
        print(f'[*] Derived {len(addresses)} total addresses')
    elif args.addresses_file:
        with open(args.addresses_file) as f:
            for line in f:
                line = line.strip()
                if line.startswith('0x'):
                    addresses.append(('manual', line))
        print(f'[*] Loaded {len(addresses)} addresses from file')
    else:
        print('Usage:')
        print('  python3 hd_wallet_scanner.py --mnemonic "twelve word phrase here ..."')
        print('  python3 hd_wallet_scanner.py --mnemonic-file ~/.seed --n 50')
        print('  python3 hd_wallet_scanner.py --addresses-file my_addrs.txt')
        sys.exit(1)

    chains = json.load(open(os.path.join(SCRIPT_DIR, 'chains.json')))['chains']
    rpcs = chains['ethereum']['rpcs']
    sem = asyncio.Semaphore(8)
    ssl_ctx = ssl.create_default_context(cafile=certifi.where())
    connector = aiohttp.TCPConnector(limit=15, ssl=ssl_ctx)

    async def runner():
        async with aiohttp.ClientSession(connector=connector) as session:
            print(f'[*] Scanning {len(addresses)} addresses against native balance + {len(CHECKS)} contracts...')
            return await scan_addresses(session, sem, rpcs, addresses)

    found = asyncio.run(runner())

    print('\n' + '=' * 70)
    if found:
        print(f'  ✓ FOUND {len(found)} positive results!')
        print('=' * 70)
        out = os.path.join(SCRIPT_DIR, 'hd_wallet_scan_results.json')
        json.dump(found, open(out, 'w'), indent=2)
        print(f'  Saved: {out}')
    else:
        print('  No funds found across all derivation paths.')
        print('=' * 70)
        print('  Suggestions:')
        print('  - Try with --n 100 (deeper derivation)')
        print('  - Verify your mnemonic word count and order')
        print('  - Try with passphrase: BIP-39 supports a 25th word')


if __name__ == '__main__':
    main()
