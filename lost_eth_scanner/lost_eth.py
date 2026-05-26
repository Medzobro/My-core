#!/usr/bin/env python3
"""
Lost ETH Scanner - main CLI entry point
=========================================
One command to access all scanners.

Usage:
    python3 lost_eth.py recover --file my_addrs.txt    # Personal recovery
    python3 lost_eth.py recover --mnemonic "..."       # HD wallet scan
    python3 lost_eth.py audit                          # Wide multichain audit
    python3 lost_eth.py deep                           # Deep audit with ERC-20
    python3 lost_eth.py mev-hunt                       # MEV-style drain hunter
    python3 lost_eth.py stuck-erc20                    # Stuck token + rescue scan
    python3 lost_eth.py cryptopunks                    # CryptoPunks pending scan
    python3 lost_eth.py etherdelta [start] [end]       # EtherDelta unclaimed scan
    python3 lost_eth.py analyze <chain> <address>      # Single-contract deep dive
    python3 lost_eth.py info                           # Show DB stats
"""
import sys
import os
import subprocess
import json

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))


def run(script, *args):
    cmd = ['python3', os.path.join(SCRIPT_DIR, script)] + list(args)
    print(f'>>> {" ".join(cmd)}')
    return subprocess.call(cmd)


def info():
    print('🏴‍☠️  Lost ETH Scanner — Database Info')
    print('=' * 60)
    chains = json.load(open(os.path.join(SCRIPT_DIR, 'data', 'chains.json')))
    contracts = json.load(open(os.path.join(SCRIPT_DIR, 'data', 'contracts_multichain.json')))
    airdrops = json.load(open(os.path.join(SCRIPT_DIR, 'data', 'contracts_airdrops.json')))
    print(f'  Chains supported:        {len(chains["chains"])}')
    print(f'  Contracts indexed:       {len(contracts["contracts"])}')
    print(f'  Airdrops indexed:        {len(airdrops["contracts"])}')
    print()
    print('Per-chain contract counts:')
    by_chain = {}
    for c in contracts['contracts']:
        if c.get('_comment'):
            continue
        by_chain.setdefault(c.get('chain', '?'), 0)
        by_chain[c['chain']] += 1
    for ch, n in sorted(by_chain.items(), key=lambda x: -x[1]):
        print(f'    {ch:12s} {n:>4}')
    print()
    cp_path = os.path.join(SCRIPT_DIR, 'results', 'cryptopunks_pending.json')
    if os.path.exists(cp_path):
        cp = json.load(open(cp_path))
        total = sum(e['pending_eth'] for e in cp)
        print(f'★ CryptoPunks unclaimed:  {len(cp)} addresses, {total:,.2f} ETH')
    print()
    print('Run `python3 lost_eth.py --help` for available commands.')


def usage():
    print(__doc__)


def main():
    if len(sys.argv) < 2:
        usage()
        return 0

    cmd = sys.argv[1].lower()
    args = sys.argv[2:]

    cmds = {
        'recover': 'check_my_addresses.py',
        'mnemonic': 'hd_wallet_scanner.py',
        'audit': 'multichain_audit.py',
        'deep': 'deep_audit.py',
        'mev-hunt': 'mev_dust_hunter.py',
        'mev': 'mev_dust_hunter.py',
        'stuck-erc20': 'stuck_erc20_hunter.py',
        'erc20': 'stuck_erc20_hunter.py',
        'cryptopunks': 'cryptopunks_pending_scan.py',
        'punks': 'cryptopunks_pending_scan.py',
        'etherdelta': 'etherdelta_quick_scan.py',
        'ed': 'etherdelta_quick_scan.py',
        'analyze': 'analyze_contract.py',
        'disasm': 'bytecode_disasm.py',
        'sources': 'source_fetcher_v2.py',
        'simulate': 'exploit_simulator.py',
        'unclaimed': 'unclaimed_balances_scan.py',
        'hunter': 'dead_contract_hunter.py',
    }

    if cmd in ('-h', '--help', 'help'):
        usage()
        return 0

    if cmd == 'info':
        info()
        return 0

    if cmd in cmds:
        return run(cmds[cmd], *args)

    print(f'Unknown command: {cmd}')
    usage()
    return 1


if __name__ == '__main__':
    sys.exit(main())
