#!/usr/bin/env python3
"""Mustahaqati CLI — one entry point for the audit engine and research tools.

Usage
-----
    python lost_eth.py audit 0xADDR [--json out.json] [--no-native]
    python lost_eth.py report 0xADDR [-o report.html]
    python lost_eth.py discover 0xADDR
    python lost_eth.py airdrops 0xADDR
    python lost_eth.py nfts 0xADDR
    python lost_eth.py scan 0xADDR            # legacy terminal scanner
    python lost_eth.py monitor 0xADDR --interval 300
    python lost_eth.py withdraw CONTRACT TOKEN WEI
    python lost_eth.py server --port 8010
    python lost_eth.py stats
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

from audit.engine import audit_address, load_data  # noqa: E402
from core.util import Colors, format_amount  # noqa: E402


def cmd_audit(args: argparse.Namespace) -> int:
    report = asyncio.run(
        audit_address(
            args.address,
            chains_filter=args.chains.split(",") if args.chains else None,
            include_native=not args.no_native,
        )
    )
    C = Colors
    print(f"\n{C.BOLD}{C.CYAN}{'=' * 72}{C.RESET}")
    print(f"  {C.BOLD}Address:{C.RESET} {report.address}")
    print(
        f"  {C.BOLD}Elapsed:{C.RESET} {report.elapsed:.2f}s   "
        f"{C.BOLD}RPC:{C.RESET} {report.stats['rpc_calls']} calls, "
        f"{report.stats['rpc_failures']} failures"
    )
    print(f"{C.CYAN}{'=' * 72}{C.RESET}\n")

    if not report.findings:
        print(f"  {C.GRAY}{report.verdict_ar}{C.RESET}\n")
    for finding in report.findings:
        colour = {"easy": C.GREEN, "medium": C.YELLOW, "hard": C.RED}.get(
            finding.difficulty, C.RESET
        )
        print(f"  {colour}*{C.RESET} {C.BOLD}{finding.contract_name}{C.RESET} [{finding.chain}]")
        print(
            f"      {C.BOLD}{format_amount(finding.amount)} {finding.symbol}{C.RESET}"
            + (f"  ~${finding.usd:,.0f}" if finding.usd else "")
            + f"   ({finding.difficulty})"
        )
        for index, step in enumerate(finding.steps, 1):
            print(f"      {index}. {step['ar']}")
        for step in finding.calldata:
            print(
                f"      {C.CYAN}{step['function']}{C.RESET} -> {step['to']}\n"
                f"        {C.GRAY}{step['data']}{C.RESET}"
            )
        if finding.note_ar:
            print(f"      {C.YELLOW}note:{C.RESET} {finding.note_ar}")
        print()

    if report.native:
        print(f"  {C.GRAY}wallet balances (context, not stuck):{C.RESET}")
        for item in report.native:
            print(f"    {item['chain']:10} {format_amount(item['amount'])} {item['symbol']}")
    print()

    if args.json:
        with open(args.json, "w", encoding="utf-8") as handle:
            json.dump(report.to_dict(), handle, indent=2, ensure_ascii=False)
        print(f"  saved: {args.json}")
    return 0


def cmd_report(args: argparse.Namespace) -> int:
    from audit.render import render_report

    report = asyncio.run(audit_address(args.address, include_native=True))
    out = args.output or f"report-{report.address[:10]}.html"
    with open(out, "w", encoding="utf-8") as handle:
        handle.write(render_report(report))
    print(f"report written: {out}")
    return 0


def cmd_scan(args: argparse.Namespace) -> int:
    from scanner_v2 import main_async

    chains = {c.strip() for c in args.chains.split(",") if c.strip()} if args.chains else None
    asyncio.run(
        main_async(
            args.addresses,
            chains,
            args.concurrency,
            args.json,
            args.watch,
            args.interval,
            not args.no_native,
        )
    )
    return 0


def cmd_discover(args: argparse.Namespace) -> int:
    from discovery import discover

    asyncio.run(discover(args.address, args.chain, args.max_contracts, args.include_l2))
    return 0


def cmd_airdrops(args: argparse.Namespace) -> int:
    from airdrop_checker import check_address

    asyncio.run(check_address(args.addresses))
    return 0


def cmd_nfts(args: argparse.Namespace) -> int:
    from nft_scanner import main_async

    asyncio.run(main_async(args.addresses))
    return 0


def cmd_monitor(args: argparse.Namespace) -> int:
    from monitor import monitor

    try:
        asyncio.run(monitor(args.addresses, args.interval, args.webhook, None, args.concurrency))
    except KeyboardInterrupt:
        print("\nstopped")
    return 0


def cmd_withdraw(args: argparse.Namespace) -> int:
    from withdraw_helper import main as withdraw_main

    sys.argv = ["withdraw_helper.py", args.contract, args.token, str(args.amount_wei)]
    withdraw_main()
    return 0


def cmd_server(args: argparse.Namespace) -> int:
    import uvicorn

    uvicorn.run("audit.server:app", host=args.host, port=args.port, log_level=args.log_level)
    return 0


def cmd_doctor(args: argparse.Namespace) -> int:
    from audit.doctor import doctor

    result = asyncio.run(doctor(concurrency=args.concurrency))
    C = Colors
    print(f"\n{C.BOLD}CONTRACT DOCTOR{C.RESET}  ({result['checked']} checks)\n")
    for item in result["contracts"]:
        if not item["is_contract"]:
            state = f"{C.RED}DEAD{C.RESET}"
        elif item["expected_found"] is False:
            state = f"{C.YELLOW}WARN{C.RESET}"
        else:
            state = f"{C.GREEN}OK  {C.RESET}"
        note = f"  {C.GRAY}{item['note']}{C.RESET}" if item["note"] else ""
        print(
            f"  {state} {item['name'][:34]:<34} {item['chain']:<10} "
            f"{item['address']} bytes={item['code_bytes']}{note}"
        )
    print(
        f"\n  {C.BOLD}{result['healthy']}{C.RESET} live · "
        f"{C.RED}{result['dead']}{C.RESET} dead · "
        f"{C.YELLOW}{result['selector_warnings']}{C.RESET} selector warnings\n"
    )
    if args.json:
        with open(args.json, "w", encoding="utf-8") as handle:
            json.dump(result, handle, indent=2, ensure_ascii=False)
        print(f"  saved: {args.json}")
    if args.fail_on_dead and (result["dead"] or result["selector_warnings"]):
        return 1
    return 0


def cmd_stats(_args: argparse.Namespace) -> int:

    chains, contracts, tokens = load_data()
    C = Colors
    print(f"{C.BOLD}DATA OVERVIEW{C.RESET}\n")
    print(f"  chains:    {len(chains)}")
    print(f"  contracts: {len(contracts)} scanned by the engine")
    print(f"  tokens:    {sum(len(t) for t in tokens.values())} across {len(tokens)} chains\n")
    by_chain: dict[str, int] = {}
    for contract in contracts:
        by_chain[contract["chain"]] = by_chain.get(contract["chain"], 0) + 1
    print(f"  by chain:  {dict(sorted(by_chain.items(), key=lambda kv: -kv[1]))}")
    print(f"  checks:    {sorted({c['balance_check'] for c in contracts if c.get('balance_check')})}\n")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="lost_eth", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    subs = parser.add_subparsers(dest="cmd", required=True)

    p = subs.add_parser("audit", help="audit an address for recoverable balances")
    p.add_argument("address")
    p.add_argument("--chains", default="")
    p.add_argument("--json", default=None)
    p.add_argument("--no-native", action="store_true", help="skip wallet balance context")
    p.set_defaults(func=cmd_audit)

    p = subs.add_parser("report", help="write a shareable HTML report")
    p.add_argument("address")
    p.add_argument("-o", "--output", default=None)
    p.set_defaults(func=cmd_report)

    p = subs.add_parser("scan", help="legacy terminal scanner (colour output)")
    p.add_argument("addresses", nargs="+")
    p.add_argument("--chains", default="")
    p.add_argument("--concurrency", type=int, default=80)
    p.add_argument("--json", default=None)
    p.add_argument("--watch", action="store_true")
    p.add_argument("--interval", type=int, default=60)
    p.add_argument("--no-native", action="store_true")
    p.set_defaults(func=cmd_scan)

    p = subs.add_parser("discover", help="derive contracts from your own tx history")
    p.add_argument("address")
    p.add_argument("--chain", default="ethereum")
    p.add_argument("--include-l2", action="store_true")
    p.add_argument("--max-contracts", type=int, default=200)
    p.set_defaults(func=cmd_discover)

    p = subs.add_parser("airdrops", help="check unclaimed airdrops")
    p.add_argument("addresses", nargs="+")
    p.set_defaults(func=cmd_airdrops)

    p = subs.add_parser("nfts", help="check NFT holdings")
    p.add_argument("addresses", nargs="+")
    p.set_defaults(func=cmd_nfts)

    p = subs.add_parser("monitor", help="re-scan on an interval and alert on changes")
    p.add_argument("addresses", nargs="+")
    p.add_argument("--interval", type=int, default=300)
    p.add_argument("--webhook", default=None)
    p.add_argument("--concurrency", type=int, default=80)
    p.set_defaults(func=cmd_monitor)

    p = subs.add_parser("withdraw", help="build raw withdraw calldata for your own funds")
    p.add_argument("contract")
    p.add_argument("token")
    p.add_argument("amount_wei")
    p.set_defaults(func=cmd_withdraw)

    p = subs.add_parser("server", help="run the web audit app")
    p.add_argument("--host", default="0.0.0.0")
    p.add_argument("--port", type=int, default=8010)
    p.add_argument("--log-level", default="info")
    p.set_defaults(func=cmd_server)

    p = subs.add_parser("doctor", help="check every scanned contract against live bytecode")
    p.add_argument("--json", default=None)
    p.add_argument("--fail-on-dead", action="store_true")
    p.add_argument("--concurrency", type=int, default=10)
    p.set_defaults(func=cmd_doctor)

    p = subs.add_parser("stats", help="show what the engine will scan")
    p.set_defaults(func=cmd_stats)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
