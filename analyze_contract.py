#!/usr/bin/env python3
"""
Ethereum Contract Forensic Analyzer
====================================
Read-only on-chain analysis of any Ethereum address.
Pulls: balance, code, ABI heuristics, recent transactions, token holdings,
events, function selectors, and creator/creation tx.

Usage:
    python3 analyze_contract.py <address>
"""

import sys
import json
import time
import requests
from typing import Any

# ---------- Configuration ----------
RPC_ENDPOINTS = [
    "https://eth.llamarpc.com",
    "https://rpc.ankr.com/eth",
    "https://ethereum-rpc.publicnode.com",
    "https://cloudflare-eth.com",
]

# Common ERC-20 / ERC-721 / common function selectors (first 4 bytes of keccak256(signature))
KNOWN_SELECTORS = {
    "0x06fdde03": "name()",
    "0x95d89b41": "symbol()",
    "0x313ce567": "decimals()",
    "0x18160ddd": "totalSupply()",
    "0x70a08231": "balanceOf(address)",
    "0xa9059cbb": "transfer(address,uint256)",
    "0x23b872dd": "transferFrom(address,address,uint256)",
    "0x095ea7b3": "approve(address,uint256)",
    "0xdd62ed3e": "allowance(address,address)",
    "0x8da5cb5b": "owner()",
    "0xf2fde38b": "transferOwnership(address)",
    "0x715018a6": "renounceOwnership()",
    "0x3ccfd60b": "withdraw()",
    "0x2e1a7d4d": "withdraw(uint256)",
    "0x51cff8d9": "withdraw(address)",
    "0xd0e30db0": "deposit()",
    "0xb6b55f25": "deposit(uint256)",
    "0x3f4ba83a": "unpause()",
    "0x8456cb59": "pause()",
    "0x40c10f19": "mint(address,uint256)",
    "0xa0712d68": "mint(uint256)",
    "0x1249c58b": "mint()",
    "0x42966c68": "burn(uint256)",
    "0x9dc29fac": "burn(address,uint256)",
    "0x6a627842": "mint(address)",
    "0xb88d4fde": "safeTransferFrom(address,address,uint256,bytes)",
    "0xe985e9c5": "isApprovedForAll(address,address)",
    "0xa22cb465": "setApprovalForAll(address,bool)",
    "0xc87b56dd": "tokenURI(uint256)",
    "0x6352211e": "ownerOf(uint256)",
    "0x55241077": "setMaxSupply(uint256)",
    "0xf340fa01": "deposit(address)",
    "0x4f1ef286": "upgradeToAndCall(address,bytes)",
    "0x3659cfe6": "upgradeTo(address)",
    "0x5c60da1b": "implementation()",
    "0xa6f9dae1": "changeOwner(address)",
    "0x80f323a7": "kill()",
    "0x41c0e1b5": "kill()",
    "0x35f46994": "die()",
    "0x9cb8a26a": "destroy()",
    "0x83197ef0": "destroy()",
}

# ---------- RPC helper ----------
class EthRPC:
    def __init__(self, endpoints: list[str]):
        self.endpoints = endpoints
        self.active = endpoints[0]
        self.id = 0

    def call(self, method: str, params: list[Any]) -> Any:
        self.id += 1
        payload = {"jsonrpc": "2.0", "method": method, "params": params, "id": self.id}
        last_err = None
        for ep in self.endpoints:
            try:
                r = requests.post(ep, json=payload, timeout=15)
                r.raise_for_status()
                data = r.json()
                if "error" in data:
                    last_err = data["error"]
                    continue
                self.active = ep
                return data["result"]
            except Exception as e:
                last_err = e
                continue
        raise RuntimeError(f"All RPCs failed. Last error: {last_err}")


# ---------- Analysis helpers ----------
def hex_to_int(h: str) -> int:
    return int(h, 16) if h and h != "0x" else 0


def wei_to_eth(wei: int) -> float:
    return wei / 1e18


def find_selectors(bytecode: str) -> list[str]:
    """
    EVM dispatch tables PUSH4 the selector before comparing.
    PUSH4 opcode = 0x63. We find every 0x63 followed by 4 bytes.
    """
    code = bytecode[2:] if bytecode.startswith("0x") else bytecode
    selectors = set()
    i = 0
    while i < len(code) - 10:
        if code[i:i+2].lower() == "63":
            sel = "0x" + code[i+2:i+10].lower()
            # heuristic: skip selectors that are clearly noise
            if sel != "0x00000000" and sel != "0xffffffff":
                selectors.add(sel)
            i += 10
        else:
            i += 2
    return sorted(selectors)


def detect_patterns(bytecode: str) -> list[str]:
    code = bytecode.lower()
    flags = []
    if "ff" in code and "selfdestruct" in code:
        flags.append("Possible SELFDESTRUCT opcode (0xff)")
    # 0xff is selfdestruct opcode
    if "f0" in code:
        pass
    # Look for raw opcode bytes
    opcodes = {
        "ff": "SELFDESTRUCT",
        "f4": "DELEGATECALL",
        "f1": "CALL",
        "f2": "CALLCODE",
        "fa": "STATICCALL",
        "f0": "CREATE",
        "f5": "CREATE2",
    }
    raw = code[2:] if code.startswith("0x") else code
    found = set()
    for i in range(0, len(raw)-1, 2):
        b = raw[i:i+2]
        if b in opcodes:
            found.add(opcodes[b])
    if found:
        flags.append("Opcodes present: " + ", ".join(sorted(found)))
    # EIP-1167 minimal proxy
    if "363d3d373d3d3d363d73" in raw:
        flags.append("EIP-1167 Minimal Proxy detected (delegates to another contract)")
    # EIP-1967 proxy storage slot
    if "360894a13ba1a3210667c828492db98dca3e2076cc3735a920a3ca505d382bbc" in raw:
        flags.append("EIP-1967 Proxy storage slot reference")
    return flags


def find_creation(rpc: EthRPC, addr: str, latest_block: int) -> dict:
    """Binary search for the contract creation block using eth_getCode."""
    print("  Searching for creation block (binary search)...")
    lo, hi = 0, latest_block
    # First check it actually has code at latest
    if rpc.call("eth_getCode", [addr, hex(latest_block)]) == "0x":
        return {"found": False, "reason": "No code at latest block (EOA or destroyed)"}
    while lo < hi:
        mid = (lo + hi) // 2
        code = rpc.call("eth_getCode", [addr, hex(mid)])
        if code == "0x":
            lo = mid + 1
        else:
            hi = mid
    creation_block = lo
    block = rpc.call("eth_getBlockByNumber", [hex(creation_block), True])
    creator = None
    creation_tx = None
    for tx in block.get("transactions", []):
        if tx.get("to") is None:
            # contract creation tx -- check receipt
            try:
                rcpt = rpc.call("eth_getTransactionReceipt", [tx["hash"]])
                if rcpt and rcpt.get("contractAddress", "").lower() == addr.lower():
                    creator = tx["from"]
                    creation_tx = tx["hash"]
                    break
            except Exception:
                continue
    return {
        "found": True,
        "block": creation_block,
        "block_timestamp": hex_to_int(block["timestamp"]),
        "creator": creator,
        "creation_tx": creation_tx,
    }


def get_recent_logs(rpc: EthRPC, addr: str, latest_block: int, lookback_blocks: int = 100000) -> list:
    """Get logs/events from this contract over recent blocks."""
    from_block = max(0, latest_block - lookback_blocks)
    try:
        logs = rpc.call("eth_getLogs", [{
            "address": addr,
            "fromBlock": hex(from_block),
            "toBlock": hex(latest_block),
        }])
        return logs or []
    except Exception as e:
        return []


# ---------- Main ----------
def analyze(addr: str):
    addr = addr.lower()
    rpc = EthRPC(RPC_ENDPOINTS)

    print(f"\n{'='*70}")
    print(f"  ETHEREUM CONTRACT FORENSIC REPORT")
    print(f"  Address: {addr}")
    print(f"{'='*70}\n")

    # 1. Latest block
    latest_hex = rpc.call("eth_blockNumber", [])
    latest = hex_to_int(latest_hex)
    print(f"[+] Connected via: {rpc.active}")
    print(f"[+] Latest block: {latest:,}\n")

    # 2. Balance
    print("--- BALANCE ---")
    bal_hex = rpc.call("eth_getBalance", [addr, "latest"])
    wei = hex_to_int(bal_hex)
    eth = wei_to_eth(wei)
    print(f"  Balance: {wei} wei")
    print(f"  Balance: {eth:.18f} ETH")

    # 3. Nonce / tx count
    nonce_hex = rpc.call("eth_getTransactionCount", [addr, "latest"])
    nonce = hex_to_int(nonce_hex)
    print(f"  Outgoing tx count (nonce): {nonce}")

    # 4. Code
    print("\n--- CODE ---")
    code = rpc.call("eth_getCode", [addr, "latest"])
    is_contract = code != "0x"
    print(f"  Is contract: {is_contract}")
    if is_contract:
        print(f"  Bytecode length: {(len(code)-2)//2} bytes")
        print(f"  Bytecode (first 120 chars): {code[:120]}...")

        # 5. Function selectors
        print("\n--- FUNCTION SELECTORS (heuristic from PUSH4) ---")
        selectors = find_selectors(code)
        print(f"  Found {len(selectors)} candidate selectors")
        identified = []
        unknown = []
        for s in selectors:
            if s in KNOWN_SELECTORS:
                identified.append((s, KNOWN_SELECTORS[s]))
            else:
                unknown.append(s)
        if identified:
            print(f"  Identified ({len(identified)}):")
            for sel, name in identified:
                print(f"    {sel}  ->  {name}")
        if unknown:
            print(f"  Unknown selectors ({len(unknown)}):")
            for s in unknown[:30]:
                print(f"    {s}")
            if len(unknown) > 30:
                print(f"    ... and {len(unknown)-30} more")
            print(f"  -> Look these up at: https://www.4byte.directory/")

        # 6. Pattern detection
        print("\n--- BYTECODE PATTERNS ---")
        flags = detect_patterns(code)
        if flags:
            for f in flags:
                print(f"  - {f}")
        else:
            print("  (no notable patterns)")

        # 7. Creation
        print("\n--- DEPLOYMENT ---")
        try:
            creation = find_creation(rpc, addr, latest)
            if creation["found"]:
                ts = creation["block_timestamp"]
                date = time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime(ts))
                age_days = (time.time() - ts) / 86400
                print(f"  Creation block: {creation['block']:,}")
                print(f"  Creation date:  {date}")
                print(f"  Age:            {age_days:.0f} days")
                print(f"  Creator:        {creation['creator']}")
                print(f"  Creation tx:    {creation['creation_tx']}")
            else:
                print(f"  {creation['reason']}")
        except Exception as e:
            print(f"  Creation search failed: {e}")

        # 8. Events
        print("\n--- RECENT EVENTS (last 100k blocks ~ 14 days) ---")
        try:
            logs = get_recent_logs(rpc, addr, latest, 100000)
            print(f"  Events found: {len(logs)}")
            if logs:
                topics_count = {}
                for log in logs:
                    if log.get("topics"):
                        t = log["topics"][0]
                        topics_count[t] = topics_count.get(t, 0) + 1
                print("  Top event signatures (topic0):")
                known_topics = {
                    "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef": "Transfer(address,address,uint256)",
                    "0x8c5be1e5ebec7d5bd14f71427d1e84f3dd0314c0f7b2291e5b200ac8c7c3b925": "Approval(address,address,uint256)",
                    "0x17307eab39ab6107e8899845ad3d59bd9653f200f220920489ca2b5937696c31": "ApprovalForAll(address,address,bool)",
                    "0x8be0079c531659141344cd1fd0a4f28419497f9722a3daafe3b4186f6b6457e0": "OwnershipTransferred(address,address)",
                    "0x7fcf532c15f0a6db0bd6d0e038bea71d30d808c7d98cb3bf7268a95bf5081b65": "Withdrawal(address,uint256)",
                    "0xe1fffcc4923d04b559f4d29a8bfc6cda04eb5b0d3c460751c2402c5c5cc9109c": "Deposit(address,uint256)",
                }
                for topic, count in sorted(topics_count.items(), key=lambda x: -x[1])[:10]:
                    name = known_topics.get(topic, "(unknown)")
                    print(f"    {topic}  x{count}  {name}")
        except Exception as e:
            print(f"  Event scan failed: {e}")

        # 9. Storage slots peek (first few)
        print("\n--- STORAGE SLOTS (slots 0-5) ---")
        for slot in range(6):
            try:
                v = rpc.call("eth_getStorageAt", [addr, hex(slot), "latest"])
                if v and v != "0x" + "00"*32:
                    print(f"  slot[{slot}] = {v}")
                else:
                    print(f"  slot[{slot}] = (empty)")
            except Exception:
                pass

        # 10. EIP-1967 proxy slots
        print("\n--- PROXY DETECTION (EIP-1967 slots) ---")
        proxy_slots = {
            "implementation": "0x360894a13ba1a3210667c828492db98dca3e2076cc3735a920a3ca505d382bbc",
            "admin":          "0xb53127684a568b3173ae13b9f8a6016e243e63b6e8ee1178d6a717850b5d6103",
            "beacon":         "0xa3f0ad74e5423aebfd80d3ef4346578335a9a72aeaee59ff6cb3582b35133d50",
        }
        is_proxy = False
        for name, slot in proxy_slots.items():
            v = rpc.call("eth_getStorageAt", [addr, slot, "latest"])
            if v and v != "0x" + "00"*32:
                # last 20 bytes is the address
                impl_addr = "0x" + v[-40:]
                print(f"  {name}: {impl_addr}")
                is_proxy = True
        if not is_proxy:
            print("  Not an EIP-1967 proxy (or implementation slot empty)")
    else:
        print("  This is an EOA (Externally Owned Account), not a contract.")

    print(f"\n{'='*70}")
    print("  Useful follow-up links:")
    print(f"  - Etherscan:        https://etherscan.io/address/{addr}")
    print(f"  - Read contract:    https://etherscan.io/address/{addr}#readContract")
    print(f"  - 4byte directory:  https://www.4byte.directory/")
    print(f"  - Decompiler:       https://library.dedaub.com/decompile  (paste bytecode)")
    print(f"  - Panoramix:        https://github.com/palkeo/panoramix   (offline decompiler)")
    print(f"{'='*70}\n")


if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else "0x2a0c0dbecc7e4d658f48e01e3fa353f44050c208"
    analyze(target)
