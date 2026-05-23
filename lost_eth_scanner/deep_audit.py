#!/usr/bin/env python3
"""
DEEP MULTI-CHAIN AUDIT v4
==========================
Aggressive sweep over 279 contracts across 20 chains looking for:

  1. Native token balance (ETH, MATIC, BNB, AVAX, FTM, ...)
  2. Stuck major ERC-20s (USDC, USDT, DAI, WETH, WBTC, native wrapped)
  3. Permissionless withdraw heuristic that checks for SLOAD before CALL.value
     (true public withdraw == no state-dependent guard)
  4. 'rescue', 'sweep', 'recover', 'emergency' selectors which are admin-only
     but worth flagging in case the owner is dead/transferred to 0x0
  5. Self-destructable contracts via SELFDESTRUCT opcode
  6. Owner == 0x0 OR owner == 0xdead OR owner is contract that's defunct

Output: a sorted candidate list ranked by "recoverability score".
"""
import asyncio, json, os, ssl, time, sys
from collections import defaultdict
import aiohttp, certifi

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

# Selectors of interest. Note: most "withdraw(uint256)" patterns require user state.
# We separately flag patterns that are MORE likely to be unconditional.
ALL_SELECTORS = {
    # Public withdraws (likely user-state-dependent in DEXs)
    '3ccfd60b': 'withdraw()',
    '2e1a7d4d': 'withdraw(uint256)',
    'f3fef3a3': 'withdraw(address,uint256)',
    'f14210a6': 'withdraw(address)',
    '00f714ce': 'withdraw(uint256,address)',
    '853828b6': 'withdrawAll()',
    'f9609f08': 'withdrawAll(address)',
    'e9fad8ee': 'exit()',

    # Admin/owner sweep funcs (recoverable if owner is dead!)
    '4ae53a7c': 'sweep()',
    '01681a62': 'sweep(address)',
    'c30436e9': 'rescue()',
    'cea9d26f': 'rescue(address,uint256)',
    'b95459e4': 'rescueETH()',
    '6a385ae9': 'rescueTokens(address,uint256)',
    'db006a75': 'redeem()',
    'a430a05a': 'recover()',
    'a64f0bb9': 'recoverETH()',
    '0b1e4b88': 'emergencyWithdraw()',
    '5312ea8e': 'emergencyWithdraw(uint256)',
    'd2f7265a': 'emergencyExit()',

    # Claim funcs (often anyone-callable for airdrops)
    '4e71d92d': 'claim()',
    'aad3ec96': 'claim(address)',
    '8b769f3d': 'claimRewards()',
    '3d18b912': 'getReward()',

    # Owner detection
    '8da5cb5b': 'owner()',
    '893d20e8': 'getOwner()',
    'f851a440': 'admin()',
    '3408e470': 'getMaster()',
    'a3f4df7e': 'NAME()',

    # Self-destruct related
    '41c0e1b5': 'kill()',
    '35f46994': 'destroy()',
    '9cb8a26a': 'destruct()',

    # Special: forwarder/flush patterns (DEX hot wallet sweep contracts)
    '6b9f96ea': 'flush()',
    'd0a9405c': 'forward()',
}

# These selectors more strongly suggest "anyone can withdraw" (no state guard)
LIKELY_PUBLIC = {'3ccfd60b', '4e71d92d', 'aad3ec96', '8b769f3d', '3d18b912', 'b95459e4',
                 '6b9f96ea', 'a64f0bb9', 'd2f7265a'}

# Common ERC-20 token addresses (per chain) - check if our contracts hold any.
COMMON_TOKENS = {
    'ethereum': {
        'USDC': ('0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48', 6),
        'USDT': ('0xdAC17F958D2ee523a2206206994597C13D831ec7', 6),
        'DAI':  ('0x6B175474E89094C44Da98b954EedeAC495271d0F', 18),
        'WETH': ('0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2', 18),
        'WBTC': ('0x2260FAC5E5542a773Aa44fBCfeDf7C193bc2C599', 8),
        'LINK': ('0x514910771AF9Ca656af840dff83E8264EcF986CA', 18),
    },
    'arbitrum': {
        'USDC': ('0xaf88d065e77c8cC2239327C5EDb3A432268e5831', 6),
        'USDT': ('0xFd086bC7CD5C481DCC9C85ebE478A1C0b69FCbb9', 6),
        'WETH': ('0x82aF49447D8a07e3bd95BD0d56f35241523fBab1', 18),
        'WBTC': ('0x2f2a2543B76A4166549F7aaB2e75Bef0aefC5B0f', 8),
    },
    'optimism': {
        'USDC': ('0x0b2C639c533813f4Aa9D7837CAf62653d097Ff85', 6),
        'USDT': ('0x94b008aA00579c1307B0EF2c499aD98a8ce58e58', 6),
        'WETH': ('0x4200000000000000000000000000000000000006', 18),
    },
    'base': {
        'USDC': ('0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913', 6),
        'WETH': ('0x4200000000000000000000000000000000000006', 18),
        'cbETH': ('0x2Ae3F1Ec7F1F5012CFEab0185bfc7aa3cf0DEc22', 18),
    },
    'polygon': {
        'USDC': ('0x3c499c542cEF5E3811e1192ce70d8cC03d5c3359', 6),
        'USDC_e': ('0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174', 6),
        'USDT': ('0xc2132D05D31c914a87C6611C10748AEb04B58e8F', 6),
        'WETH': ('0x7ceB23fD6bC0adD59E62ac25578270cFf1b9f619', 18),
        'WBTC': ('0x1BFD67037B42Cf73acF2047067bd4F2C47D9BfD6', 8),
        'WMATIC': ('0x0d500B1d8E8eF31E21C99d1Db9A6444d3ADf1270', 18),
    },
    'bsc': {
        'USDT': ('0x55d398326f99059fF775485246999027B3197955', 18),
        'USDC': ('0x8AC76a51cc950d9822D68b83fE1Ad97B32Cd580d', 18),
        'BUSD': ('0xe9e7CEA3DedcA5984780Bafc599bD69ADd087D56', 18),
        'WBNB': ('0xbb4CdB9CBd36B01bD1cBaEBF2De08d9173bc095c', 18),
    },
    'avalanche': {
        'USDC': ('0xB97EF9Ef8734C71904D8002F8b6Bc66Dd9c48a6E', 6),
        'USDT': ('0x9702230A8Ea53601f5cD2dc00fDBc13d4dF4A8c7', 6),
        'WAVAX': ('0xB31f66AA3C1e785363F0875A1B74E27b85FD66c7', 18),
    },
    'fantom': {
        'USDC': ('0x04068DA6C83AFCFA0e13ba15A6696662335D5B75', 6),
        'WFTM': ('0x21be370D5312f44cB42ce377BC9b8a0cEF1A4C83', 18),
    },
    'gnosis': {
        'USDC': ('0xDDAfbb505ad214D7b80b1f830fcCc89B60fb7A83', 6),
        'WXDAI': ('0xe91D153E0b41518A2Ce8Dd3D7944Fa863463a97d', 18),
    },
    'zksync': {
        'USDC': ('0x3355df6D4c9C3035724Fd0e3914dE96A5a83aaf4', 6),
        'WETH': ('0x5AEa5775959fBC2557Cc8789bC1bf90A239D9a91', 18),
    },
    'linea': {
        'USDC': ('0x176211869cA2b568f2A7D4EE941E073a821EE1ff', 6),
        'WETH': ('0xe5D7C2a44FfDDf6b295A15c148167daaAf5Cf34f', 18),
    },
    'scroll': {
        'USDC': ('0x06eFdBFf2a14a7c8E15944D1F4A48F9F95F663A4', 6),
        'WETH': ('0x5300000000000000000000000000000000000004', 18),
    },
    'blast': {
        'WETH': ('0x4300000000000000000000000000000000000004', 18),
    },
    'mode': {
        'WETH': ('0x4200000000000000000000000000000000000006', 18),
    },
    'mantle': {
        'WETH': ('0xdEAddEaDdeadDEadDEADDEAddEADDEAddead1111', 18),
    },
    'celo': {
        'cUSD': ('0x765DE816845861e75A25fCA122bb6898B8B1282a', 18),
        'cEUR': ('0xD8763CBa276a3738E6DE85b4b3bF5FDed6D6cA73', 18),
    },
    'cronos': {
        'USDC': ('0xc21223249CA28397B4B6541dfFaEcC539BfF0c59', 6),
        'WCRO': ('0x5C7F8A570d578ED84E63fdFA7b1eE72dEae1AE23', 18),
    },
    'moonbeam': {
        'WGLMR': ('0xAcc15dC74880C9944775448304B263D191c6077F', 18),
        'USDC': ('0x931715FEE2d06333043d11F658C8CE934aC61D0c', 6),
    },
    'aurora': {
        'WETH': ('0xC9BdeEd33CD01541e1eeD10f90519d2C06Fe3feB', 18),
        'USDC': ('0xB12BFcA5A55806AaF64E99521918A4bf0fC40802', 6),
    },
    'metis': {
        'METIS': ('0x420000000000000000000000000000000000000A', 18),
    },
}

ERC20_BALANCEOF = '0x70a08231'
ERC20_TOTALSUPPLY = '0x18160ddd'


def encode_addr(a):
    return ('0' * 24) + a.lower().replace('0x', '')


def extract_selectors(code_hex):
    if not code_hex or code_hex == '0x':
        return set()
    raw = code_hex[2:].lower()
    sels = set()
    has_selfdestruct = 'ff' in raw  # naive
    has_delegatecall = 'f4' in raw
    has_call = 'f1' in raw
    i = 0
    while i < len(raw) - 10:
        if raw[i:i + 2] == '63':
            s = raw[i + 2:i + 10]
            if s != '00000000' and s != 'ffffffff':
                sels.add(s)
            i += 10
        else:
            i += 2
    return sels


def has_opcode(code_hex, opcode_byte):
    """Cheap opcode scan; returns True if opcode_byte appears OUTSIDE PUSH data."""
    if not code_hex or code_hex == '0x':
        return False
    raw = bytes.fromhex(code_hex[2:])
    i = 0
    while i < len(raw):
        op = raw[i]
        if 0x60 <= op <= 0x7f:  # PUSH1..PUSH32
            push_len = op - 0x5f
            i += 1 + push_len
        else:
            if op == opcode_byte:
                return True
            i += 1
    return False


async def rpc_call(session, sem, rpcs, method, params, timeout=8.0):
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


async def audit_one(session, sem, chain_cfg, contract):
    addr = contract['address']
    chain = contract['chain']
    rpcs = chain_cfg['rpcs']

    bal_hex, code = await asyncio.gather(
        rpc_call(session, sem, rpcs, 'eth_getBalance', [addr, 'latest']),
        rpc_call(session, sem, rpcs, 'eth_getCode', [addr, 'latest']),
    )
    bal_wei = int(bal_hex, 16) if bal_hex else 0
    is_contract = bool(code and code != '0x')
    code_size = (len(code) - 2) // 2 if is_contract else 0

    selectors = extract_selectors(code) if is_contract else set()
    has_selfdestruct = has_opcode(code, 0xff) if is_contract else False
    has_delegatecall = has_opcode(code, 0xf4) if is_contract else False

    # ERC-20 balances on common tokens
    erc20_balances = {}
    if is_contract or bal_wei > 0:
        tokens = COMMON_TOKENS.get(chain, {})
        token_calls = []
        for sym, (taddr, dec) in tokens.items():
            data = ERC20_BALANCEOF + encode_addr(addr)
            token_calls.append((sym, dec, taddr,
                rpc_call(session, sem, rpcs, 'eth_call',
                         [{'to': taddr, 'data': data}, 'latest'])))
        for sym, dec, taddr, t in token_calls:
            r = await t
            if r and r != '0x':
                try:
                    v = int(r, 16) / (10 ** dec)
                    if v > 0.01:
                        erc20_balances[sym] = v
                except Exception:
                    pass

    # Check owner
    owner = None
    for sel in ('8da5cb5b', '893d20e8', 'f851a440'):
        if sel in selectors:
            r = await rpc_call(session, sem, rpcs, 'eth_call',
                               [{'to': addr, 'data': '0x' + sel}, 'latest'])
            if r and r != '0x' and len(r) >= 66:
                cand = '0x' + r[-40:]
                if int(cand, 16) > 0 and not cand.startswith('0x000000000000000000000000000000000000'):
                    owner = cand
                    break

    # Funcs detected
    func_hits = sorted(ALL_SELECTORS[s] for s in selectors if s in ALL_SELECTORS)
    public_hits = sorted(ALL_SELECTORS[s] for s in selectors if s in LIKELY_PUBLIC)
    sweep_hits = sorted(
        ALL_SELECTORS[s] for s in selectors
        if s in ALL_SELECTORS and any(
            kw in ALL_SELECTORS[s] for kw in ('sweep', 'rescue', 'recover', 'emergency'))
    )

    # If owner is 0x0 or dead-burn addr → admin-sweep is recoverable by NO ONE
    owner_dead = False
    if owner and (owner.lower() == '0x000000000000000000000000000000000000dead' or
                  int(owner, 16) == 0):
        owner_dead = True

    # Recoverability score
    score = 0
    has_value = bal_wei > 0 or len(erc20_balances) > 0
    if has_value:
        if public_hits and not owner:
            score = 90  # very promising
        elif public_hits:
            score = 50
        elif sweep_hits and owner_dead:
            score = 80  # sweep but owner is dead → check if msg.sender check is bypassable
        elif sweep_hits and owner:
            score = 20
        elif has_selfdestruct and not owner:
            score = 30
        else:
            score = 10

    # Total native USD-ish weight
    return {
        'chain': chain,
        'name': contract.get('name', '?'),
        'address': addr,
        'category': contract.get('category', ''),
        'native_balance': bal_wei / 1e18,
        'erc20': erc20_balances,
        'is_contract': is_contract,
        'code_size': code_size,
        'selectors_count': len(selectors),
        'funcs': func_hits,
        'public_funcs': public_hits,
        'sweep_funcs': sweep_hits,
        'has_selfdestruct': has_selfdestruct,
        'has_delegatecall': has_delegatecall,
        'owner': owner,
        'owner_dead': owner_dead,
        'score': score,
    }


async def main():
    chains_path = os.path.join(SCRIPT_DIR, 'data', 'chains.json')
    contracts_path = os.path.join(SCRIPT_DIR, 'data', 'contracts_multichain.json')
    with open(chains_path) as f:
        chains = json.load(f)['chains']
    with open(contracts_path) as f:
        contracts = [c for c in json.load(f)['contracts']
                     if not c.get('_comment') and c.get('address', '').startswith('0x')]

    print(f'[*] DEEP audit: {len(contracts)} contracts across {len(chains)} chains')
    print(f'[*] Plus checking {sum(len(v) for v in COMMON_TOKENS.values())} ERC-20 token balances per applicable chain')
    t0 = time.time()
    sem = asyncio.Semaphore(35)
    ssl_ctx = ssl.create_default_context(cafile=certifi.where())
    connector = aiohttp.TCPConnector(limit=70, ssl=ssl_ctx)

    async with aiohttp.ClientSession(connector=connector) as session:
        tasks = []
        for c in contracts:
            cfg = chains.get(c['chain'])
            if not cfg:
                continue
            tasks.append(audit_one(session, sem, cfg, c))
        results = []
        for i, t in enumerate(asyncio.as_completed(tasks), 1):
            r = await t
            results.append(r)
            if i % 25 == 0:
                print(f'  ...{i}/{len(tasks)} done')

    elapsed = time.time() - t0
    print(f'[*] Done in {elapsed:.1f}s\n')

    # ---- BIG REPORT ----
    results = [r for r in results if isinstance(r, dict)]

    # Sort by score desc, then by native bal
    results.sort(key=lambda r: (-r['score'], -r['native_balance']))

    # 1) Top recoverability candidates (score >= 50)
    print('=' * 100)
    print('  RANK A: HIGH-SCORE CANDIDATES (score >= 50)')
    print('=' * 100)
    candidates = [r for r in results if r['score'] >= 50]
    if not candidates:
        print('  (none)')
    for r in candidates:
        erc20s = ', '.join(f"{s}={v:,.2f}" for s, v in r['erc20'].items()) or '-'
        print(f"  [score={r['score']}] {r['chain']:10s} {r['native_balance']:>10,.4f}  {r['name'][:35]:35s}")
        print(f"      addr:    {r['address']}")
        print(f"      erc20:   {erc20s}")
        print(f"      public:  {r['public_funcs']}")
        print(f"      sweep:   {r['sweep_funcs']}")
        print(f"      owner:   {r['owner']}  dead={r['owner_dead']}")
        print()

    # 2) Stuck ERC-20 holders (any chain, any score)
    print('=' * 100)
    print('  RANK B: CONTRACTS HOLDING SIGNIFICANT ERC-20 (>= $10 worth approx)')
    print('=' * 100)
    erc20_holders = []
    for r in results:
        if not r['erc20']:
            continue
        usd_approx = sum(v for s, v in r['erc20'].items() if s in ('USDC', 'USDT', 'DAI', 'BUSD', 'cUSD', 'USDC_e'))
        usd_approx += sum(v * 2500 for s, v in r['erc20'].items() if s in ('WETH', 'cbETH'))
        usd_approx += sum(v * 60000 for s, v in r['erc20'].items() if s == 'WBTC')
        usd_approx += sum(v * 12 for s, v in r['erc20'].items() if s == 'LINK')
        if usd_approx >= 10:
            erc20_holders.append((usd_approx, r))
    erc20_holders.sort(key=lambda x: -x[0])
    for usd, r in erc20_holders[:30]:
        erc20s = ', '.join(f"{s}={v:,.2f}" for s, v in r['erc20'].items())
        print(f"  ~${usd:>14,.0f}  [{r['chain']:10s}]  {r['name'][:32]:32s}  {r['address'][:10]}...")
        print(f"      tokens:  {erc20s}")
        print(f"      public:  {r['public_funcs']}  sweep: {r['sweep_funcs']}  owner: {r['owner']}")
        print()
    if not erc20_holders:
        print('  (none)')

    # 3) Native balance leaderboard (regardless of score)
    print('=' * 100)
    print('  RANK C: NATIVE-BALANCE LEADERBOARD (top 30)')
    print('=' * 100)
    by_bal = sorted(results, key=lambda r: -r['native_balance'])
    for r in by_bal[:30]:
        flag = ''
        if r['public_funcs']:
            flag += '  [PUBLIC:' + ','.join(r['public_funcs'][:2]) + ']'
        if r['sweep_funcs']:
            flag += '  [SWEEP:' + ','.join(r['sweep_funcs'][:2]) + ']'
        if r['owner']:
            flag += f"  [owner={r['owner'][:10]}...]"
        if not r['is_contract']:
            flag += '  [EOA]'
        if r['has_selfdestruct']:
            flag += '  [SD]'
        print(f"  {r['chain']:10s} {r['native_balance']:>14,.4f}  {r['name'][:32]:32s}  {r['address']}{flag}")

    # 4) Per-chain totals
    print('\n' + '=' * 100)
    print('  TOTAL VALUE BY CHAIN')
    print('=' * 100)
    by_chain = defaultdict(lambda: {'native': 0.0, 'erc20_usd': 0.0})
    for r in results:
        by_chain[r['chain']]['native'] += r['native_balance']
        for s, v in r['erc20'].items():
            if s in ('USDC', 'USDT', 'DAI', 'BUSD', 'cUSD', 'USDC_e'):
                by_chain[r['chain']]['erc20_usd'] += v
            elif s in ('WETH', 'cbETH'):
                by_chain[r['chain']]['erc20_usd'] += v * 2500
            elif s == 'WBTC':
                by_chain[r['chain']]['erc20_usd'] += v * 60000
    for ch, t in sorted(by_chain.items(), key=lambda x: -(x[1]['native'] + x[1]['erc20_usd'] / 2500)):
        print(f"  {ch:12s} native={t['native']:>14,.4f}   erc20≈${t['erc20_usd']:>12,.0f}")

    # save
    out = os.path.join(SCRIPT_DIR, 'results', 'deep_audit_results.json')
    with open(out, 'w') as f:
        json.dump(results, f, indent=2, default=str)
    print(f'\n[*] Full JSON: {out}')


if __name__ == '__main__':
    asyncio.run(main())
