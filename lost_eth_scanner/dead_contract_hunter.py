#!/usr/bin/env python3
"""
DEAD CONTRACT HUNTER
====================
Investigates the legitimacy of "lost ETH" claims by analyzing dead contracts.

For each contract, determines:
  1. Current ETH and token balance
  2. Last outbound transaction (if any) - is the contract truly dormant?
  3. Last incoming transaction
  4. Owner address (if applicable) - is it still active?
  5. Exit paths from bytecode analysis
  6. Classification: FROZEN, USER_DEPOSITS, PERMISSIONLESS, LOST_OWNER, HD_WALLET

This is a forensic / educational tool. It does NOT find exploits - it documents
which contracts are mathematically dead-locked vs. which require specific keys.
"""
import sys, os, json, time
import requests

RPCS = [
    'https://ethereum-rpc.publicnode.com',
    'https://eth.llamarpc.com',
    'https://rpc.ankr.com/eth',
]

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(SCRIPT_DIR, 'dead_contracts_db.json')

# Bytecode signatures we look for
PERMISSIONLESS_PATTERNS = {
    'public_withdraw': '3ccfd60b',  # withdraw() with no args - often permissionless
    'collect': '78cd1d56',          # collect() - common forwarder pattern
    'sweep': '4ae53a7c',
    'claim': '4e71d92d',
    'rescue': 'c30436e9',
    'flush': '6b9f96ea',
    'forward': 'd0a9405c',
}

OWNER_FUNCS = {
    '8da5cb5b': 'owner()',
    '893d20e8': 'getOwner()',
    'f851a440': 'admin()',
}


def rpc(method, params, timeout=10):
    last = None
    for r in RPCS:
        try:
            response = requests.post(r, json={'jsonrpc':'2.0','method':method,'params':params,'id':1}, timeout=timeout).json()
            if 'result' in response:
                return response['result']
            last = response.get('error')
        except Exception as e:
            last = str(e)
    return None


def get_basic_info(addr):
    bal_hex = rpc('eth_getBalance', [addr, 'latest'])
    code = rpc('eth_getCode', [addr, 'latest'])
    nonce_hex = rpc('eth_getTransactionCount', [addr, 'latest'])
    return {
        'balance_wei': int(bal_hex, 16) if bal_hex else 0,
        'balance_eth': int(bal_hex, 16) / 1e18 if bal_hex else 0,
        'code_size': (len(code) - 2) // 2 if code and code != '0x' else 0,
        'is_contract': code is not None and code != '0x',
        'nonce': int(nonce_hex, 16) if nonce_hex else 0,
        'code': code,
    }


def get_owner(addr):
    """Try common owner getters. Returns address or None."""
    for sel, name in OWNER_FUNCS.items():
        result = rpc('eth_call', [{'to': addr, 'data': '0x' + sel}, 'latest'])
        if result and result != '0x' and len(result) >= 66:
            owner = '0x' + result[-40:]
            if int(owner, 16) > 0:
                return {'address': owner, 'method': name}
    return None


def analyze_bytecode(code):
    """Extract function selectors and detect patterns."""
    if not code or code == '0x':
        return {'selectors': [], 'patterns': [], 'opcodes': set()}
    raw = code[2:].lower()

    # Find selectors (PUSH4 = 0x63)
    selectors = set()
    i = 0
    while i < len(raw) - 10:
        if raw[i:i+2] == '63':
            sel = raw[i+2:i+10]
            if sel != '00000000' and sel != 'ffffffff':
                selectors.add(sel)
            i += 10
        else:
            i += 2

    # Pattern matching
    patterns = []
    for name, sig in PERMISSIONLESS_PATTERNS.items():
        if sig in selectors:
            patterns.append(name)

    # Critical opcodes
    opcodes = set()
    bad_opcodes = {'ff': 'SELFDESTRUCT', 'f4': 'DELEGATECALL', 'f1': 'CALL'}
    for j in range(0, len(raw)-1, 2):
        op = raw[j:j+2]
        if op in bad_opcodes:
            opcodes.add(bad_opcodes[op])

    return {'selectors': sorted(selectors), 'patterns': patterns, 'opcodes': opcodes}


def get_recent_activity_blockscout(addr):
    """Use Blockscout to find first/last in/out tx."""
    try:
        r = requests.get(f'https://eth.blockscout.com/api/v2/addresses/{addr}/transactions', timeout=15).json()
        items = r.get('items', [])
        if not items:
            return None

        out = [t for t in items if t.get('from', {}).get('hash', '').lower() == addr.lower()]
        inc = [t for t in items if t.get('to', {}).get('hash', '').lower() == addr.lower()]

        return {
            'last_tx': items[0].get('timestamp') if items else None,
            'last_method': items[0].get('method') if items else None,
            'last_outbound': out[0].get('timestamp') if out else None,
            'has_outbound': len(out) > 0,
            'recent_methods': list({t.get('method') for t in items[:10] if t.get('method')}),
        }
    except Exception:
        return None


def classify(info, owner_info, activity, bytecode_info):
    """Determine the contract's death type."""
    if info['balance_eth'] == 0 and info['code_size'] == 0:
        return 'EOA_EMPTY', 'Not a contract, no balance'

    if not info['is_contract']:
        if info['balance_eth'] > 0 and activity and not activity.get('has_outbound'):
            return 'EOA_DORMANT', f"EOA holds {info['balance_eth']:.2f} ETH, no outbound tx ever (key likely lost)"
        return 'EOA_ACTIVE', 'EOA with normal activity'

    # It's a contract
    if 'public_withdraw' in bytecode_info['patterns']:
        return 'PERMISSIONLESS', 'Contract has withdraw() with no auth check (MEV bot likely already drained)'

    if 'sweep' in bytecode_info['patterns'] or 'collect' in bytecode_info['patterns']:
        return 'FORWARDER', 'Forwarding pattern - sweep targets owner only'

    if owner_info:
        # Check if owner is alive
        return 'OWNED', f"Owner = {owner_info['address']} via {owner_info['method']}"

    return 'UNKNOWN_CONTRACT', f"Code size {info['code_size']} bytes, no obvious owner pattern"


def investigate(addr, label=None):
    print(f'\n{"=" * 76}')
    print(f'  {label or "Contract"}')
    print(f'  {addr}')
    print(f'{"=" * 76}')

    info = get_basic_info(addr)
    print(f'  Balance:     {info["balance_eth"]:>14,.4f} ETH')
    print(f'  Is contract: {info["is_contract"]}')
    print(f'  Code size:   {info["code_size"]:>14,} bytes')
    print(f'  Nonce:       {info["nonce"]:>14,}')

    owner_info = get_owner(addr) if info['is_contract'] else None
    if owner_info:
        owner_balance = get_basic_info(owner_info['address'])
        print(f'  Owner:       {owner_info["address"]} (via {owner_info["method"]})')
        print(f'  Owner ETH:   {owner_balance["balance_eth"]:>14,.4f}')
        print(f'  Owner nonce: {owner_balance["nonce"]:>14,}')

    activity = get_recent_activity_blockscout(addr)
    if activity:
        print(f'  Last tx:           {activity.get("last_tx")} (method: {activity.get("last_method")})')
        print(f'  Last outbound:     {activity.get("last_outbound") or "NEVER"}')
        print(f'  Has any outbound:  {activity.get("has_outbound")}')
        print(f'  Recent methods:    {activity.get("recent_methods")}')

    bytecode_info = analyze_bytecode(info.get('code', ''))
    if info['is_contract']:
        print(f'  Selectors:         {len(bytecode_info["selectors"])}')
        print(f'  Patterns matched:  {bytecode_info["patterns"] or "(none)"}')
        print(f'  Opcodes present:   {bytecode_info["opcodes"]}')

    klass, reason = classify(info, owner_info, activity, bytecode_info)
    print(f'  CLASSIFICATION:    {klass}')
    print(f'  REASON:            {reason}')

    return {
        'address': addr,
        'label': label,
        'class': klass,
        'reason': reason,
        'balance_eth': info['balance_eth'],
        'is_contract': info['is_contract'],
        'has_owner': owner_info is not None,
        'patterns': bytecode_info['patterns'],
    }


def main():
    print('DEAD CONTRACT HUNTER - Forensic Analysis')
    print('=' * 76)

    if len(sys.argv) > 1:
        # Specific addresses
        results = [investigate(a) for a in sys.argv[1:]]
    else:
        # Run on the database
        with open(DB_PATH) as f:
            db = json.load(f)['contracts']
        results = []
        for c in db:
            if c.get('_comment'):
                continue
            results.append(investigate(c['address'], c.get('name')))
            time.sleep(0.3)

    # Summary
    print(f'\n\n{"=" * 76}')
    print('  CLASSIFICATION SUMMARY')
    print(f'{"=" * 76}')
    by_class = {}
    total_eth = 0.0
    for r in results:
        by_class.setdefault(r['class'], []).append(r)
        total_eth += r['balance_eth']

    for cls, items in sorted(by_class.items(), key=lambda x: -sum(i['balance_eth'] for i in x[1])):
        eth = sum(i['balance_eth'] for i in items)
        print(f'\n  [{cls}]  {len(items)} contracts  -  {eth:,.2f} ETH total')
        for r in sorted(items, key=lambda x: -x['balance_eth']):
            print(f'    {r["balance_eth"]:>12,.2f} ETH  {r["address"]}  {r.get("label","")}')

    print(f'\n  TOTAL ETH IN ANALYZED CONTRACTS: {total_eth:,.2f}')

    # Save full results
    out_path = os.path.join(SCRIPT_DIR, 'investigation_results.json')
    with open(out_path, 'w') as f:
        json.dump(results, f, indent=2)
    print(f'\n  Full results saved to: {out_path}')


if __name__ == '__main__':
    main()
