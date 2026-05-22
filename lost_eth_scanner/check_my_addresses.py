#!/usr/bin/env python3
"""
CHECK MY ADDRESSES - Personal recovery tool
=============================================
Drop a list of YOUR Ethereum addresses (from old wallets, exchanges, MetaMask
backups, etc.) into MY_ADDRESSES below or pass --file path/to/addresses.txt
(one address per line). The tool checks every known abandoned-DEX contract
for unclaimed balances tied to those addresses.

What it checks:
  1. EtherDelta v1, v2, v3 / ForkDelta - tokens[0x0][user]
  2. IDEX 1.0 - tokens[0x0][user]
  3. Token.Store - tokens[0x0][user]
  4. CryptoPunks pendingWithdrawals (V1 + V2)
  5. Compound v1 cETH balance
  6. WithdrawDAO via DAO token balance
"""
import asyncio, json, os, ssl, sys
import aiohttp, certifi

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

# ⚠️ EDIT THIS LIST WITH YOUR OLD ETHEREUM ADDRESSES ⚠️
MY_ADDRESSES = [
    # '0xYourOldAddress1...',
    # '0xYourOldAddress2...',
]


# Contracts we check (Ethereum mainnet)
CHECKS = [
    {
        'name': 'EtherDelta v1', 'addr': '0x8da0d80f5007ef1e431dd2127178d224e32c2ef4',
        'method': 'tokens(address,address)', 'sel': '0xf7888aec', 'arg': 'token_user',
    },
    {
        'name': 'EtherDelta v2', 'addr': '0x4aBB0f5fd529cD8C3F80FB6C2e5249084B7CfA63',
        'method': 'tokens(address,address)', 'sel': '0xf7888aec', 'arg': 'token_user',
    },
    {
        'name': 'ForkDelta / EtherDelta v3', 'addr': '0x8d12A197cB00D4747a1fe03395095ce2A5CC6819',
        'method': 'tokens(address,address)', 'sel': '0xf7888aec', 'arg': 'token_user',
    },
    {
        'name': 'IDEX 1.0', 'addr': '0x2a0c0DBEcC7E4D658f48E01e3fA353F44050c208',
        'method': 'tokens(address,address)', 'sel': '0xf7888aec', 'arg': 'token_user',
    },
    {
        'name': 'Token.Store', 'addr': '0x1ce7AE555139c5EF5A57CC8d814a867ee6Ee33D8',
        'method': 'tokens(address,address)', 'sel': '0xf7888aec', 'arg': 'token_user',
    },
    {
        'name': 'CryptoPunks V2 pendingWithdrawals', 'addr': '0xb47e3cd837dDF8e4c57F05d70Ab865de6e193BBB',
        'method': 'pendingWithdrawals(address)', 'sel': '0xf3f43703', 'arg': 'user',
    },
    {
        'name': 'CryptoPunks V1 pendingWithdrawals', 'addr': '0x6BA6f2207e343923BA692e5Cae646Fb0F566DB8D',
        'method': 'pendingWithdrawals(address)', 'sel': '0xf3f43703', 'arg': 'user',
    },
    {
        'name': 'Compound v1 cETH balance', 'addr': '0x3FDA67f7583380E67ef93072294a7fAc882FD7E7',
        'method': 'balanceOf(address)', 'sel': '0x70a08231', 'arg': 'user', 'decimals': 8,
    },
    {
        'name': 'WithdrawDAO eligibility (DAO token)', 'addr': '0xbb9bc244d798123fde783fcc1c72d3bb8c189413',
        'method': 'balanceOf(address)', 'sel': '0x70a08231', 'arg': 'user', 'decimals': 16,
    },
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


def load_addresses():
    if len(sys.argv) > 1 and sys.argv[1] == '--file' and len(sys.argv) > 2:
        with open(sys.argv[2]) as f:
            return [l.strip() for l in f if l.strip().startswith('0x')]
    return MY_ADDRESSES


async def main():
    addresses = load_addresses()
    if not addresses:
        print('=' * 70)
        print('  No addresses configured.')
        print('=' * 70)
        print('  Edit MY_ADDRESSES list in this file, OR run:')
        print('     python3 check_my_addresses.py --file my_addrs.txt')
        print('  (one address per line, plain text, starting with 0x)')
        return

    chains = json.load(open(os.path.join(SCRIPT_DIR, 'chains.json')))['chains']
    rpcs = chains['ethereum']['rpcs']
    sem = asyncio.Semaphore(10)
    ssl_ctx = ssl.create_default_context(cafile=certifi.where())
    connector = aiohttp.TCPConnector(limit=20, ssl=ssl_ctx)

    print(f'[*] Checking {len(addresses)} address(es) across {len(CHECKS)} contracts on Ethereum mainnet...\n')

    found = []
    async with aiohttp.ClientSession(connector=connector) as session:
        for user in addresses:
            print(f'== {user} ==')
            any_hit = False
            for chk in CHECKS:
                bal = await check_one(session, sem, rpcs, chk['addr'], user, chk['sel'], chk['arg'])
                if bal > 0:
                    any_hit = True
                    decimals = chk.get('decimals', 18)
                    val = bal / (10 ** decimals)
                    note = ''
                    if 'pendingWithdrawals' in chk['name']:
                        note = '  (call withdraw() to claim)'
                    elif 'tokens' in chk['method']:
                        note = '  (call withdraw(uint256) to claim)'
                    elif 'WithdrawDAO' in chk['name']:
                        note = '  (call withdraw() on 0xbf4ed7b27f1d666546e30d74d50d173d20bca754; pays 1 ETH / 100 DAO)'
                    elif 'Compound' in chk['name']:
                        note = '  (call redeem(uint256) on cETH to convert to ETH)'
                    print(f'  ★★ {chk["name"]:42s}: {val:>16,.6f}  {note}')
                    found.append({'address': user, 'contract': chk['name'],
                                   'contract_addr': chk['addr'], 'amount': val, 'wei': str(bal)})
            if not any_hit:
                print('   (nothing)')
            print()

    if found:
        print('=' * 70)
        print('  ✓ RECOVERABLE FUNDS DETECTED!')
        print('=' * 70)
        for f in found:
            print(f"  {f['address']}  {f['contract']}: {f['amount']}")
        out = os.path.join(SCRIPT_DIR, 'my_recoverables.json')
        with open(out, 'w') as fp:
            json.dump(found, fp, indent=2)
        print(f'\n[*] Saved: {out}')
        print('\nHOW TO RECOVER:')
        print('  1. Make sure you have the PRIVATE KEY for the address above')
        print('  2. Use the relevant withdraw method:')
        print('     - EtherDelta/ForkDelta/IDEX/Token.Store: contract.withdraw(amount)')
        print('     - CryptoPunks: contract.withdraw()')
        print('     - WithdrawDAO: contract.withdraw() at 0xbf4ed7b2...')
        print('     - Compound v1 cETH: contract.redeem(amount) at 0x3FDA67f7...')
        print('  3. Pay gas, the ETH lands in your wallet')
    else:
        print('\n[*] No recoverable funds for these addresses.')
        print('    Try with more old addresses you may have forgotten about:')
        print('    - Old MetaMask exports / keystore JSON files')
        print("    - Mist wallet pre-2018")
        print("    - Hardware wallet derivation paths (m/44'/60'/0'/0/0..N)")
        print("    - Old MyEtherWallet / MyCrypto JSON")
        print("    - 2017-era ICO contribution addresses")


if __name__ == '__main__':
    asyncio.run(main())
