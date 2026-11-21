#!/usr/bin/env python3
"""
LEAKED KEYS CROSS-REFERENCE
=============================
Some Ethereum addresses are known to be associated with publicly-leaked
private keys. These keys appear in:

  1. Default Hardhat / Ganache / Truffle test accounts (mnemonic = 'test test
     test test test test test test test test test junk')
  2. Trivial integer private keys (1, 2, 3, ...)
  3. Famous demo / tutorial keys (committed to GitHub publicly)
  4. Profanity-tool weak vanity keys (cracked Sept 2022)

If any of our unclaimed-balance addresses match a leaked-key address, the funds
are CRYPTOGRAPHICALLY recoverable - anyone with the leaked key can withdraw.

This is forensic exposure, not active exploitation.

Reference: github.com/AnacondaWasTaken/EthereumPrivateKey-Search
"""
import json
import os
import hashlib

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))


# Known leaked/weak addresses (public knowledge, all keys leaked years ago)
KNOWN_LEAKED_ADDRESSES = {
    # Trivial integer private keys 1..20 (pre-computed addresses)
    # priv_key = 1 -> addr 0x7E5F4552091A69125d5DfCb7b8C2659029395Bdf
    '0x7e5f4552091a69125d5dfcb7b8c2659029395bdf': 'priv_key=1 (TRIVIAL)',
    '0x2b5ad5c4795c026514f8317c7a215e218dccd6cf': 'priv_key=2 (TRIVIAL)',
    '0x6813eb9362372eef6200f3b1dbc3f819671cba69': 'priv_key=3 (TRIVIAL)',
    '0x1eff47bc3a10a45d4b230b5d10e37751fe6aa718': 'priv_key=4 (TRIVIAL)',
    '0xe1ab8145f7e55dc933d51a18c793f901a3a0b276': 'priv_key=5 (TRIVIAL)',
    '0xe57bfe9f44b819898f47bf37e5af72a0783e1141': 'priv_key=6 (TRIVIAL)',
    '0xd41c057fd1c78805aac12b0a94a405c0461a6fbb': 'priv_key=7 (TRIVIAL)',
    '0xf1f6619b38a98d6de0800f1defc0a6399eb6d30c': 'priv_key=8 (TRIVIAL)',
    '0xf7edc8fa1ecc32967f827c9043fcae6ba73afa5c': 'priv_key=9 (TRIVIAL)',
    '0x4f8be1bd0b7c79f1e3aa4a51b91a40ff1c2acb6e': 'priv_key=10 (TRIVIAL)',

    # Hardhat default mnemonic accounts (test test test ... junk)
    # acct 0..19
    '0xf39fd6e51aad88f6f4ce6ab8827279cfffb92266': 'Hardhat default acct 0',
    '0x70997970c51812dc3a010c7d01b50e0d17dc79c8': 'Hardhat default acct 1',
    '0x3c44cdddb6a900fa2b585dd299e03d12fa4293bc': 'Hardhat default acct 2',
    '0x90f79bf6eb2c4f870365e785982e1f101e93b906': 'Hardhat default acct 3',
    '0x15d34aaf54267db7d7c367839aaf71a00a2c6a65': 'Hardhat default acct 4',
    '0x9965507d1a55bcc2695c58ba16fb37d819b0a4dc': 'Hardhat default acct 5',
    '0x976ea74026e726554db657fa54763abd0c3a0aa9': 'Hardhat default acct 6',
    '0x14dc79964da2c08b23698b3d3cc7ca32193d9955': 'Hardhat default acct 7',
    '0x23618e81e3f5cdf7f54c3d65f7fbc0abf5b21e8f': 'Hardhat default acct 8',
    '0xa0ee7a142d267c1f36714e4a8f75612f20a79720': 'Hardhat default acct 9',

    # Ganache deterministic mode default (mnemonic: 'myth like bonus scare ...')
    # different deterministic seed
    '0x90f8bf6a479f320ead074411a4b0e7944ea8c9c1': 'Ganache deterministic acct 0',
    '0xffcf8fdee72ac11b5c542428b35eef5769c409f0': 'Ganache deterministic acct 1',
    '0x22d491bde2303f2f43325b2108d26f1eaba1e32b': 'Ganache deterministic acct 2',

    # Famous Github-leaked keys (publicly known)
    '0x0000000000000000000000000000000000000000': 'NULL (burn)',
    '0x000000000000000000000000000000000000dead': 'BURN (dead)',

    # Vitalik's old test address (publicly known as test)
    # NOT a leak per se but commonly spoofed

    # Some addresses associated with truffle-config.js leaks (publicly indexed)
    # (these are NOT real keys but have appeared in many tutorials)
    '0x627306090abab3a6e1400e9345bc60c78a8bef57': 'Truffle tutorial demo acct 0',
    '0xf17f52151ebef6c7334fad080c5704d77216b732': 'Truffle tutorial demo acct 1',
}


def main():
    # Load all unclaimed balance lists we have
    sources = []

    cp_path = os.path.join(SCRIPT_DIR, 'results', 'cryptopunks_pending.json')
    if os.path.exists(cp_path):
        cp = json.load(open(cp_path))
        for e in cp:
            sources.append({
                'addr': e['seller'].lower(),
                'amount': e['pending_eth'],
                'source': f'CryptoPunks pendingWithdrawals ({e.get("contract", "?")})',
            })

    ed_path = os.path.join(SCRIPT_DIR, 'results',
                           'etherdelta_unclaimed_4700000_4720000.json')
    if os.path.exists(ed_path):
        ed = json.load(open(ed_path))
        for e in ed:
            sources.append({
                'addr': e['user'].lower(),
                'amount': e['eth'],
                'source': 'EtherDelta v3 user balance (sample 4.7M-4.72M)',
            })

    print(f'[*] Cross-referencing {len(sources)} unclaimed-balance addresses')
    print(f'[*] Against {len(KNOWN_LEAKED_ADDRESSES)} known leaked / weak addresses\n')

    hits = []
    for s in sources:
        if s['addr'].lower() in KNOWN_LEAKED_ADDRESSES:
            label = KNOWN_LEAKED_ADDRESSES[s['addr'].lower()]
            hits.append({**s, 'leak_type': label})

    print('=' * 100)
    print('  RESULTS')
    print('=' * 100)
    if hits:
        print(f'  ★★★ {len(hits)} HITS - addresses with publicly-known keys hold unclaimed funds!\n')
        for h in hits:
            print(f"    {h['amount']:>10,.4f} ETH  {h['addr']}")
            print(f"      Source:    {h['source']}")
            print(f"      Leak:      {h['leak_type']}")
            print()
    else:
        print(f'  No matches found - none of the {len(sources)} unclaimed addresses use known leaked keys.')

    # Also analyze: how many distinct unclaimed addresses we have total
    print(f'\n  Statistical summary:')
    print(f'    Total unclaimed addresses scanned: {len(sources)}')
    distinct = set(s['addr'].lower() for s in sources)
    print(f'    Distinct addresses:               {len(distinct)}')

    out = os.path.join(SCRIPT_DIR, 'results', 'leaked_keys_results.json')
    json.dump(hits, open(out, 'w'), indent=2)
    print(f'\n[*] Saved: {out}')


if __name__ == '__main__':
    main()
