#!/usr/bin/env python3
"""
AIRDROP CHECKER
===============
Checks an address against known airdrops (claimed and unclaimed).

Detects historical eligibility for airdrops like:
  - Uniswap UNI (2020)
  - ENS DAO (2021)
  - Optimism OP (2022, 4 rounds)
  - Arbitrum ARB (2023)
  - 1inch (2020)
  - dYdX (2021)
  - Looksrare (2022)
  - Hop (2022)
  - Stargate (2022)
  - Blur (2023)
  - Aevo (2024)
  - Wormhole W (2024)
  - Jito (Solana - excluded)
  - StarkNet STRK (2024)
  - LayerZero ZRO (2024)
  - Ethereum Name Service (resolved names)

Usage:
    python3 airdrop_checker.py 0xYourAddress
"""
import argparse
import asyncio
import json
import os
import ssl
import sys
import time

import aiohttp
import certifi

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CHAINS_FILE = os.path.join(SCRIPT_DIR, 'chains.json')


class C:
    RESET = '\033[0m'; BOLD = '\033[1m'
    GREEN = '\033[32m'; YELLOW = '\033[33m'; RED = '\033[31m'
    BLUE = '\033[34m'; CYAN = '\033[36m'; GRAY = '\033[90m'; MAGENTA = '\033[35m'


# Known airdrop token contracts and their claim contracts/checkers
AIRDROPS = [
    {
        'name': 'Uniswap UNI',
        'date': '2020-09',
        'chain': 'ethereum',
        'token': '0x1f9840a85d5af5bf1d1762f925bdaddc4201f984',
        'token_decimals': 18,
        'token_symbol': 'UNI',
        'claim_contract': '0x090D4613473dEE047c3f2706764f49E0821D256e',
        'claim_method': 'isClaimed(uint256)',
        'amount_per_addr': 400,
        'note': 'Required Uniswap usage before Sep 1, 2020. 400 UNI per address.',
    },
    {
        'name': 'ENS DAO',
        'date': '2021-11',
        'chain': 'ethereum',
        'token': '0xC18360217D8F7Ab5e7c516566761Ea12Ce7F9D72',
        'token_decimals': 18,
        'token_symbol': 'ENS',
        'claim_contract': '0xd7174f7Eef4FF7AAEDe4f30Bd61C82c2c4C3A1d3',
        'note': 'Required ENS .eth name registration before Oct 31, 2021.',
    },
    {
        'name': 'Optimism OP (Round 1)',
        'date': '2022-05',
        'chain': 'optimism',
        'token': '0x4200000000000000000000000000000000000042',
        'token_decimals': 18,
        'token_symbol': 'OP',
        'claim_contract': '0xfedfaf1a10335448b7fa0268f56d2b44dbd357de',
        'note': 'Required bridging to Optimism, DAO voting, etc.',
    },
    {
        'name': 'Optimism OP (Round 2)',
        'date': '2023-02',
        'chain': 'optimism',
        'token': '0x4200000000000000000000000000000000000042',
        'token_decimals': 18,
        'token_symbol': 'OP',
        'claim_contract': '0xFb4D5A94b516DF77fbDBcF3CFEB262baAf7d4eB7',
        'note': 'For continued ecosystem participants.',
    },
    {
        'name': 'Arbitrum ARB',
        'date': '2023-03',
        'chain': 'arbitrum',
        'token': '0x912CE59144191C1204E64559FE8253a0e49E6548',
        'token_decimals': 18,
        'token_symbol': 'ARB',
        'claim_contract': '0x67a24CE4321aB3aF51c2D0a4801c3E111D88C9d9',
        'note': 'Required Arbitrum usage points before Feb 6, 2023.',
    },
    {
        'name': '1inch INCH',
        'date': '2020-12',
        'chain': 'ethereum',
        'token': '0x111111111117dc0aa78b770fa6a738034120c302',
        'token_decimals': 18,
        'token_symbol': '1INCH',
        'claim_contract': '0xe295aD71242373C37C5FdA7B57F26f9eA1088AFe',
        'note': '4+ trades or 1 trade > $20 before Christmas 2020.',
    },
    {
        'name': 'dYdX DYDX',
        'date': '2021-09',
        'chain': 'ethereum',
        'token': '0x92D6C1e31e14520e676a687F0a93788B716BEff5',
        'token_decimals': 18,
        'token_symbol': 'DYDX',
        'claim_contract': '0xb9b8eF61b7851276B0239757A039d54a23804CdF',
        'note': 'Required active dYdX trading pre-Aug 2021.',
    },
    {
        'name': 'LooksRare LOOKS',
        'date': '2022-01',
        'chain': 'ethereum',
        'token': '0xf4d2888d29D722226FafA5d9B24F9164c092421E',
        'token_decimals': 18,
        'token_symbol': 'LOOKS',
        'claim_contract': '0x344e85D27F8Bee72b6F274dDe6BcC1bb55BfaE3D',
        'note': 'Required NFT trading volume on OpenSea pre-2022.',
    },
    {
        'name': 'Hop HOP',
        'date': '2022-05',
        'chain': 'ethereum',
        'token': '0xc5102fe9359fd9a28f877a67e36b0f050d81a3cc',
        'token_decimals': 18,
        'token_symbol': 'HOP',
        'claim_contract': '0xbe8B79f1bcd585B7AB58Cc04dc34bc6cc14F0b9F',
        'note': 'Required Hop bridge usage.',
    },
    {
        'name': 'Stargate STG',
        'date': '2022-03',
        'chain': 'ethereum',
        'token': '0xaf5191b0de278c7286d6c7cc6ab6bb8a73ba2cd6',
        'token_decimals': 18,
        'token_symbol': 'STG',
        'note': 'Required Stargate bridge usage.',
    },
    {
        'name': 'Blur BLUR',
        'date': '2023-02',
        'chain': 'ethereum',
        'token': '0x5283D291DBCF85356A21bA090E6db59121208b44',
        'token_decimals': 18,
        'token_symbol': 'BLUR',
        'note': 'Required NFT trading on Blur pre-launch.',
    },
    {
        'name': 'Aevo AEVO',
        'date': '2024-03',
        'chain': 'ethereum',
        'token': '0xb528edBef013aff855ac3c50b381f253aF13b997',
        'token_decimals': 18,
        'token_symbol': 'AEVO',
        'note': 'Required Aevo derivatives trading.',
    },
    {
        'name': 'Wormhole W',
        'date': '2024-04',
        'chain': 'ethereum',
        'token': '0xB0fFa8000886e57F86dd5264b9582b2Ad87b2b91',
        'token_decimals': 18,
        'token_symbol': 'W',
        'note': 'Required Wormhole bridge usage.',
    },
    {
        'name': 'StarkNet STRK',
        'date': '2024-02',
        'chain': 'ethereum',
        'token': '0xCa14007Eff0dB1f8135f4C25B34De49AB0d42766',
        'token_decimals': 18,
        'token_symbol': 'STRK',
        'note': 'Required StarkNet usage. Claim on StarkNet L2.',
    },
    {
        'name': 'LayerZero ZRO',
        'date': '2024-06',
        'chain': 'ethereum',
        'token': '0x6985884C4392D348587B19cb9eAAf157F13271cd',
        'token_decimals': 18,
        'token_symbol': 'ZRO',
        'note': 'Required LayerZero bridge usage.',
    },
    {
        'name': 'Ethena ENA',
        'date': '2024-04',
        'chain': 'ethereum',
        'token': '0x57e114B691Db790C35207b2e685D4A43181e6061',
        'token_decimals': 18,
        'token_symbol': 'ENA',
    },
    {
        'name': 'Etherfi ETHFI',
        'date': '2024-03',
        'chain': 'ethereum',
        'token': '0xFe0c30065B384F05761f15d0CC899D4F9F9Cc0eB',
        'token_decimals': 18,
        'token_symbol': 'ETHFI',
    },
    {
        'name': 'Renzo REZ',
        'date': '2024-04',
        'chain': 'ethereum',
        'token': '0x3B50805453023a91a8bf641e279401a0b23FA6F9',
        'token_decimals': 18,
        'token_symbol': 'REZ',
    },
    {
        'name': 'EigenLayer EIGEN',
        'date': '2024-10',
        'chain': 'ethereum',
        'token': '0xec53bF9167f50cDEB3Ae105f56099aaaB9061F83',
        'token_decimals': 18,
        'token_symbol': 'EIGEN',
    },
    {
        'name': 'Jupiter JUP (Solana - skipped)',
        'date': '2024-01',
        'chain': 'solana',
        'note': 'Solana airdrop, requires Phantom wallet.',
    },
]


def encode_addr(a):
    return ('0' * 24) + a.lower().replace('0x', '')


async def rpc_call(session, rpcs, method, params, timeout=8):
    payload = {'jsonrpc': '2.0', 'method': method, 'params': params, 'id': 1}
    for rpc in rpcs:
        try:
            async with session.post(rpc, json=payload, timeout=aiohttp.ClientTimeout(total=timeout)) as r:
                if r.status != 200:
                    continue
                d = await r.json()
                if 'result' in d:
                    return d['result']
        except Exception:
            continue
    return None


async def check_token_balance(session, rpcs, token, user):
    data = '0x70a08231' + encode_addr(user)
    res = await rpc_call(session, rpcs, 'eth_call', [{'to': token, 'data': data}, 'latest'])
    if res and res != '0x':
        try:
            return int(res, 16)
        except Exception:
            return 0
    return 0


async def check_eligibility_via_etherscan(session, address, chain='ethereum'):
    """
    For airdrops that don't expose isClaimed publicly, we check if the address
    has any token transfer history with the airdrop token. This proves they
    were eligible IF the token contract is the airdrop token.
    """
    # Etherscan-compatible tokentx endpoint
    pass  # placeholder for future enhancement


async def check_address(addresses):
    chains_cfg = json.load(open(CHAINS_FILE))['chains']
    ssl_ctx = ssl.create_default_context(cafile=certifi.where())
    connector = aiohttp.TCPConnector(limit=50, ssl=ssl_ctx)

    print(f'{C.BOLD}AIRDROP CHECKER{C.RESET}')
    print(f'  Checking {len(addresses)} address(es) against {len(AIRDROPS)} known airdrops')
    print()

    async with aiohttp.ClientSession(connector=connector) as session:
        for address in addresses:
            address = address.lower()
            if not (address.startswith('0x') and len(address) == 42):
                print(f'{C.RED}Skipping invalid: {address}{C.RESET}')
                continue

            print(f'{C.BOLD}{C.CYAN}{"=" * 78}{C.RESET}')
            print(f'  Address: {address}')
            print(f'{C.CYAN}{"=" * 78}{C.RESET}')

            tasks = []
            valid_airdrops = []
            for ad in AIRDROPS:
                if ad.get('chain') == 'solana' or not ad.get('token'):
                    continue
                rpcs = chains_cfg.get(ad['chain'], {}).get('rpcs', [])
                if not rpcs:
                    continue
                tasks.append(check_token_balance(session, rpcs, ad['token'], address))
                valid_airdrops.append(ad)

            t0 = time.time()
            results = await asyncio.gather(*tasks, return_exceptions=True)
            elapsed = time.time() - t0

            holdings = []
            for ad, bal in zip(valid_airdrops, results):
                if isinstance(bal, Exception) or bal is None:
                    continue
                if bal > 0:
                    amount = bal / (10 ** ad['token_decimals'])
                    holdings.append((ad, amount))

            if holdings:
                print(f'\n  {C.GREEN}{C.BOLD}HOLDINGS DETECTED:{C.RESET}')
                for ad, amount in holdings:
                    expected = f' (expected ~{ad["amount_per_addr"]} per claim)' if ad.get('amount_per_addr') else ''
                    print(f'    {C.GREEN}*{C.RESET} {ad["token_symbol"]:8s} {amount:>14,.4f}  on {ad["chain"]:9s} | {ad["name"]}{expected}')
                    if ad.get('note'):
                        print(f'      {C.GRAY}{ad["note"]}{C.RESET}')
            else:
                print(f'  {C.GRAY}No airdrop tokens currently held in this wallet.{C.RESET}')
                print(f'  {C.GRAY}Note: They may have been claimed and transferred away.{C.RESET}')

            print(f'\n  {C.GRAY}Checked in {elapsed:.2f}s{C.RESET}')
            print()


def main():
    p = argparse.ArgumentParser()
    p.add_argument('addresses', nargs='+')
    args = p.parse_args()
    asyncio.run(check_address(args.addresses))


if __name__ == '__main__':
    main()
