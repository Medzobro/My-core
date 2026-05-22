#!/usr/bin/env python3
"""
LOST ETH - Master CLI
=====================
Unified command-line interface for the entire Lost ETH toolkit.

Subcommands:
  scan       - Scan addresses for stuck balances on contracts
  airdrops   - Check airdrop token holdings
  nfts       - Check NFT holdings
  monitor    - Continuous monitoring with diff detection
  hunt       - Forensic classification of dead contracts
  withdraw   - Generate raw transaction data
  api        - Start REST API server
  hd         - HD wallet bulk scan from address list
  stats      - Show database statistics

Examples:
  lost_eth.py scan 0xAddr1 0xAddr2
  lost_eth.py airdrops 0xAddr
  lost_eth.py nfts 0xAddr
  lost_eth.py monitor 0xAddr --interval 60
  lost_eth.py withdraw 0xCONTRACT 0xTOKEN 1000000000000000000
  lost_eth.py api
  lost_eth.py stats
"""
import argparse
import asyncio
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def cmd_stats(args):
    """Show database statistics."""
    from scanner_v2 import load_config, C
    chains, contracts, tokens = load_config()
    print(f'{C.BOLD}LOST ETH DATABASE STATS{C.RESET}\n')
    print(f'  Chains:    {len(chains)}')
    for k, v in chains.items():
        print(f'    {k:12s}  chainId={v.get("chain_id"):<6}  rpcs={len(v.get("rpcs",[]))}  native={v.get("native_token")}')
    print(f'\n  Contracts: {len(contracts)}')
    by_chain = {}
    by_cat = {}
    total_eth = 0
    for c in contracts:
        by_chain[c.get('chain','?')] = by_chain.get(c.get('chain','?'),0)+1
        by_cat[c.get('category','?')] = by_cat.get(c.get('category','?'),0)+1
        total_eth += c.get('balance_eth', 0)
    print(f'    By chain:    {dict(sorted(by_chain.items(), key=lambda x:-x[1]))}')
    print(f'    By category: {dict(sorted(by_cat.items(), key=lambda x:-x[1]))}')
    print(f'    Known stuck ETH: {total_eth:,}')
    print(f'\n  Tokens:    {sum(len(t) for t in tokens.values())} across {len(tokens)} chains')
    for ch, toks in tokens.items():
        print(f'    {ch:12s}  {len(toks)} tokens')


def cmd_scan(args):
    from scanner_v2 import main_async
    chains_filter = set(c.strip() for c in args.chains.split(',') if c.strip()) if args.chains else None
    asyncio.run(main_async(args.addresses, chains_filter, args.concurrency,
                            args.json, args.watch, args.interval, args.include_native))


def cmd_airdrops(args):
    from airdrop_checker import check_address
    asyncio.run(check_address(args.addresses))


def cmd_nfts(args):
    from nft_scanner import main_async
    asyncio.run(main_async(args.addresses))


def cmd_monitor(args):
    from monitor import monitor
    chains_filter = set(c.strip() for c in args.chains.split(',') if c.strip()) if args.chains else None
    try:
        asyncio.run(monitor(args.addresses, args.interval, args.webhook, chains_filter, args.concurrency))
    except KeyboardInterrupt:
        print('\nStopped.')


def cmd_hunt(args):
    from dead_contract_hunter import investigate
    if args.addresses:
        results = [investigate(a) for a in args.addresses]
    else:
        from dead_contract_hunter import main as hunt_main
        hunt_main()


def cmd_withdraw(args):
    from withdraw_helper import main as wh_main
    sys.argv = ['withdraw_helper.py', args.contract, args.token, str(args.amount_wei)]
    wh_main()


def cmd_api(args):
    try:
        import uvicorn
    except ImportError:
        print('Install: pip install fastapi uvicorn')
        return
    from api_server import app
    uvicorn.run(app, host=args.host, port=args.port)


def cmd_hd(args):
    from scanner_v2 import main_async
    addresses = list(args.addresses or [])
    if args.addresses_file:
        with open(args.addresses_file) as f:
            for line in f:
                line = line.strip()
                if line.startswith('0x') and len(line) == 42:
                    addresses.append(line)
    if not addresses:
        print('No addresses provided.')
        return
    print(f'HD Wallet Bulk Scan - {len(addresses)} addresses')
    asyncio.run(main_async(addresses, None, args.concurrency, args.json, False, 0, True))


def main():
    p = argparse.ArgumentParser(prog='lost_eth', description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sp = p.add_subparsers(dest='cmd', required=True)

    # scan
    s = sp.add_parser('scan', help='Scan addresses for stuck balances')
    s.add_argument('addresses', nargs='+')
    s.add_argument('--chains', default='')
    s.add_argument('--concurrency', type=int, default=80)
    s.add_argument('--json', default=None)
    s.add_argument('--include-native', action='store_true')
    s.add_argument('--watch', action='store_true')
    s.add_argument('--interval', type=int, default=60)
    s.set_defaults(func=cmd_scan)

    # airdrops
    s = sp.add_parser('airdrops', help='Check airdrop holdings')
    s.add_argument('addresses', nargs='+')
    s.set_defaults(func=cmd_airdrops)

    # nfts
    s = sp.add_parser('nfts', help='Check NFT holdings')
    s.add_argument('addresses', nargs='+')
    s.set_defaults(func=cmd_nfts)

    # monitor
    s = sp.add_parser('monitor', help='Continuous watch with alerts')
    s.add_argument('addresses', nargs='+')
    s.add_argument('--interval', type=int, default=300)
    s.add_argument('--webhook', default=None)
    s.add_argument('--chains', default='')
    s.add_argument('--concurrency', type=int, default=80)
    s.set_defaults(func=cmd_monitor)

    # hunt
    s = sp.add_parser('hunt', help='Forensic classify contracts')
    s.add_argument('addresses', nargs='*')
    s.set_defaults(func=cmd_hunt)

    # withdraw
    s = sp.add_parser('withdraw', help='Generate raw withdraw tx data')
    s.add_argument('contract')
    s.add_argument('token')
    s.add_argument('amount_wei')
    s.set_defaults(func=cmd_withdraw)

    # api
    s = sp.add_parser('api', help='Start REST API server')
    s.add_argument('--host', default='0.0.0.0')
    s.add_argument('--port', type=int, default=8000)
    s.set_defaults(func=cmd_api)

    # hd
    s = sp.add_parser('hd', help='Bulk scan many addresses (HD wallet style)')
    s.add_argument('addresses', nargs='*')
    s.add_argument('--addresses-file', default=None)
    s.add_argument('--concurrency', type=int, default=120)
    s.add_argument('--json', default=None)
    s.set_defaults(func=cmd_hd)

    # stats
    s = sp.add_parser('stats', help='Show database statistics')
    s.set_defaults(func=cmd_stats)

    args = p.parse_args()
    args.func(args)


if __name__ == '__main__':
    main()
