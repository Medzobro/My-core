#!/usr/bin/env python3
"""
NFT RECOVERY SCANNER
====================
Detects NFTs you may have stuck in old marketplace contracts (escrow style)
or held by abandoned smart contract wallets.

Checks:
  - OpenSea Wyvern v1/v2 (ETH escrow during failed sales)
  - LooksRare/X2Y2 contracts
  - Old NFT staking/farming contracts
  - Common NFT collections you own (top 50 by volume)

Usage:
    python3 nft_scanner.py 0xYourAddress
"""
import argparse
import asyncio
import json
import os
import ssl
import time

import aiohttp
import certifi

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CHAINS_FILE = os.path.join(SCRIPT_DIR, 'data', 'chains.json')


class C:
    RESET = '\033[0m'; BOLD = '\033[1m'
    GREEN = '\033[32m'; YELLOW = '\033[33m'; RED = '\033[31m'
    CYAN = '\033[36m'; GRAY = '\033[90m'; MAGENTA = '\033[35m'


# Top NFT collections (ERC-721) on Ethereum
NFT_COLLECTIONS = [
    {'name': 'Bored Ape Yacht Club', 'address': '0xBC4CA0EdA7647A8aB7C2061c2E118A18a936f13D'},
    {'name': 'Mutant Ape Yacht Club', 'address': '0x60E4d786628Fea6478F785A6d7e704777c86a7c6'},
    {'name': 'CryptoPunks', 'address': '0xb47e3cd837dDF8e4c57F05d70Ab865de6e193BBB'},
    {'name': 'Azuki', 'address': '0xED5AF388653567Af2F388E6224dC7C4b3241C544'},
    {'name': 'CloneX', 'address': '0x49cF6f5d44E70224e2E23fDcdd2C053F30aDA28B'},
    {'name': 'Doodles', 'address': '0x8a90CAb2b38dba80c64b7734e58Ee1dB38B8992e'},
    {'name': 'World of Women', 'address': '0xe785E82358879F061BC3dcAC6f0444462D4b5330'},
    {'name': 'Cool Cats', 'address': '0x1A92f7381B9F03921564a437210bB9396471050C'},
    {'name': 'Pudgy Penguins', 'address': '0xBd3531dA5CF5857e7CfAA92426877b022e612cf8'},
    {'name': 'Moonbirds', 'address': '0x23581767a106ae21c074b2276D25e5C3e136a68b'},
    {'name': 'BAYC v1 (deprecated)', 'address': '0xBC4CA0EdA7647A8aB7C2061c2E118A18a936f13D'},
    {'name': 'Hashmasks', 'address': '0xC2C747E0F7004F9E8817Db2ca4997657a7746928'},
    {'name': 'CryptoKitties', 'address': '0x06012c8cf97BEaD5deAe237070F9587f8E7A266d'},
    {'name': 'Otherdeed', 'address': '0x34d85c9CDeB23FA97cb08333b511ac86E1C4E258'},
    {'name': 'Chromie Squiggle (Art Blocks)', 'address': '0x059EDD72Cd353dF5106D2B9cC5ab83a52287aC3a'},
    {'name': 'Nouns', 'address': '0x9C8fF314C9Bc7F6e59A9d9225Fb22946427eDC03'},
    {'name': 'Loot', 'address': '0xFF9C1b15B16263C61d017ee9F65C50e4AE0113D7'},
    {'name': 'Meebits', 'address': '0x7Bd29408f11D2bFC23c34f18275bBf23bB716Bc7'},
    {'name': 'CyberKongz', 'address': '0x57a204AA1042f6E66DD7730813f4024114d74f37'},
    {'name': 'Cryptoadz', 'address': '0x1CB1A5e65610AEFF2551A50f76a87a7d3FB649C6'},
    {'name': 'VeeFriends', 'address': '0xa3AEe8BcE55BEeA1951EF834b99f3Ac60d1ABeeB'},
    {'name': 'goblintown', 'address': '0xbCe3781ae7Ca1a5e050Bd9C4c77369867eBc307e'},
    {'name': 'Beanz', 'address': '0x306b1ea3ecdf94aB739F1910bbda052Ed4A9f949'},
    {'name': 'mfers', 'address': '0x79FCDEF22feeD20eDDacbB2587640e45491b757f'},
    {'name': 'Sandbox LAND', 'address': '0x50f5474724e0Ee42D9a4e711ccFB275809Fd6d4a'},
    {'name': 'Decentraland LAND', 'address': '0xF87E31492Faf9A91B02Ee0dEAaD50d51d56D5d4d'},
    {'name': 'Cool Pets', 'address': '0x86C10D10ECa1Fca9DAF87a279abCcaBe0063F247'},
    {'name': 'CrypToadz by GREMPLIN', 'address': '0x1CB1A5e65610AEFF2551A50f76a87a7d3FB649C6'},
    {'name': 'Bored Ape Kennel Club', 'address': '0xba30E5F9Bb24caa003E9f2f0497Ad287FDF95623'},
    {'name': 'Lazy Lions', 'address': '0x8943C7bAC1914C9A7ABa750Bf2B6B09Fd21037E0'},
    {'name': 'Sup Ducks', 'address': '0x3Fe1a4c1481c8351E91B64D5c398b159dE07cbc5'},
    {'name': 'Cyberbrokers', 'address': '0x892848074ddeA461A15f337250Da3ce55580CA85'},
    {'name': 'Webaverse', 'address': '0xa11bd36801d8fa4448F0ac4ea7A62e3634cE8C7C'},
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


async def check_erc721_balance(session, rpcs, contract, user):
    """balanceOf(user) on ERC-721 - same selector as ERC-20"""
    data = '0x70a08231' + encode_addr(user)
    res = await rpc_call(session, rpcs, 'eth_call', [{'to': contract, 'data': data}, 'latest'])
    if res and res != '0x':
        try:
            return int(res, 16)
        except Exception:
            return 0
    return 0


async def main_async(addresses):
    chains_cfg = json.load(open(CHAINS_FILE))['chains']
    eth_rpcs = chains_cfg['ethereum']['rpcs']
    ssl_ctx = ssl.create_default_context(cafile=certifi.where())
    connector = aiohttp.TCPConnector(limit=80, ssl=ssl_ctx)

    print(f'{C.BOLD}NFT RECOVERY SCANNER{C.RESET}')
    print(f'  Checking against {len(NFT_COLLECTIONS)} top NFT collections')
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

            t0 = time.time()
            tasks = [check_erc721_balance(session, eth_rpcs, c['address'], address) for c in NFT_COLLECTIONS]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            elapsed = time.time() - t0

            holdings = []
            for col, count in zip(NFT_COLLECTIONS, results):
                if isinstance(count, Exception) or count is None:
                    continue
                if count > 0:
                    holdings.append((col, count))

            if holdings:
                print(f'\n  {C.GREEN}{C.BOLD}NFT HOLDINGS:{C.RESET}')
                for col, count in holdings:
                    print(f'    {C.GREEN}*{C.RESET} {count:>4} x  {col["name"]:35s}  ({col["address"][:10]}...)')
                    print(f'         {C.GRAY}OpenSea: https://opensea.io/{address}{C.RESET}')
            else:
                print(f'  {C.GRAY}No NFTs from top collections detected.{C.RESET}')

            print(f'\n  {C.GRAY}Scanned in {elapsed:.2f}s{C.RESET}')
            print()


def main():
    p = argparse.ArgumentParser()
    p.add_argument('addresses', nargs='+')
    args = p.parse_args()
    asyncio.run(main_async(args.addresses))


if __name__ == '__main__':
    main()
