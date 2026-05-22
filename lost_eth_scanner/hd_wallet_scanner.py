#!/usr/bin/env python3
"""
HD WALLET SCANNER
=================
Generates many addresses from a single seed phrase or xpub and scans each one.

CRITICAL SECURITY NOTE:
  - Never enter your seed phrase on an internet-connected machine.
  - This tool can take a list of ADDRESSES (already-derived) as input.
  - For seed-phrase derivation, use a hardware wallet's "show addresses" feature
    or run derivation OFFLINE on an air-gapped machine, then paste the addresses here.

Usage:
    python3 hd_wallet_scanner.py 0xAddr1 0xAddr2 ... 0xAddr50
    python3 hd_wallet_scanner.py --addresses-file addresses.txt
"""
import argparse
import asyncio
import os
import sys

# Reuse scanner_v2
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from scanner_v2 import main_async, C


def main():
    p = argparse.ArgumentParser(description='HD Wallet bulk scanner')
    p.add_argument('addresses', nargs='*', help='Addresses to scan')
    p.add_argument('--addresses-file', help='File with one address per line')
    p.add_argument('--chains', default='', help='Comma-separated chains')
    p.add_argument('--concurrency', type=int, default=120)
    p.add_argument('--include-native', action='store_true', default=True)
    p.add_argument('--json', default=None)
    args = p.parse_args()

    addresses = list(args.addresses)
    if args.addresses_file:
        with open(args.addresses_file) as f:
            for line in f:
                line = line.strip()
                if line.startswith('0x') and len(line) == 42:
                    addresses.append(line)

    if not addresses:
        print('No addresses provided.')
        return

    print(f'{C.BOLD}HD WALLET BULK SCAN{C.RESET}')
    print(f'  Scanning {len(addresses)} address(es) in parallel')
    print()

    chains_filter = set(c.strip() for c in args.chains.split(',') if c.strip()) if args.chains else None

    asyncio.run(main_async(addresses, chains_filter, args.concurrency, args.json,
                            False, 0, args.include_native))


if __name__ == '__main__':
    main()
