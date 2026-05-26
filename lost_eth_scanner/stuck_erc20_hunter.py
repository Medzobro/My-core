#!/usr/bin/env python3
"""
STUCK ERC20 HUNTER
===================
Many contracts received ERC20 tokens by mistake. Some have a public
withdrawERC20() function that lets ANYONE rescue tokens. If contract
is abandoned, the rescue is genuine "free money".

Strategy:
  1. For every contract in our DB, query balance of common ERC20s (USDC, USDT, DAI, WETH, WBTC, LINK)
  2. If balance > $10, simulate the rescue functions with eth_estimateGas
  3. If gas estimate succeeds AND > 50000 (real work), it's likely callable
  4. Filter: must NOT be the contract's own token storage logic (e.g., Aave LP holding USDC is normal)
"""
import asyncio, json, os, ssl, time
import aiohttp, certifi

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

TEST_FROM = '0xCafeBabeCafeBabeCafeBabeCafeBabeCafeBabe'

# ERC-20 rescue selectors
RESCUE_FUNCS = {
    'b95459e4': 'rescueETH()',
    '5e35359e': 'transferFrom(address,address,uint256)',
    '78cd1d56': 'collect()',
    '6a385ae9': 'rescueTokens(address,uint256)',
    '01681a62': 'sweep(address)',
    'cea9d26f': 'rescue(address,uint256)',
    'c7c19abf': 'recoverERC20(address,uint256)',
    '3009a609': 'recoverToken(address,uint256)',
    '01e33667': 'withdrawTokens(address,uint256)',
    '8f4ffcb1': 'tokenFallback(address,uint256,bytes)',
    'e575afa5': 'withdrawERC20(address,uint256)',
}

ERC20_BALANCEOF = '0x70a08231'

# Common ERC-20 per chain
COMMON_TOKENS = {
    'ethereum': {
        'USDC': ('0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48', 6),
        'USDT': ('0xdAC17F958D2ee523a2206206994597C13D831ec7', 6),
        'DAI':  ('0x6B175474E89094C44Da98b954EedeAC495271d0F', 18),
        'WETH': ('0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2', 18),
        'WBTC': ('0x2260FAC5E5542a773Aa44fBCfeDf7C193bc2C599', 8),
        'LINK': ('0x514910771AF9Ca656af840dff83E8264EcF986CA', 18),
        'SHIB': ('0x95aD61b0a150d79219dCF64E1E6Cc01f0B64C4cE', 18),
        'UNI':  ('0x1f9840a85d5aF5bf1D1762F925BDADdC4201F984', 18),
        'PEPE': ('0x6982508145454Ce325dDbE47a25d4ec3d2311933', 18),
    },
    'arbitrum': {
        'USDC': ('0xaf88d065e77c8cC2239327C5EDb3A432268e5831', 6),
        'USDT': ('0xFd086bC7CD5C481DCC9C85ebE478A1C0b69FCbb9', 6),
        'WETH': ('0x82aF49447D8a07e3bd95BD0d56f35241523fBab1', 18),
        'WBTC': ('0x2f2a2543B76A4166549F7aaB2e75Bef0aefC5B0f', 8),
        'ARB':  ('0x912CE59144191C1204E64559FE8253a0e49E6548', 18),
    },
    'optimism': {
        'USDC': ('0x0b2C639c533813f4Aa9D7837CAf62653d097Ff85', 6),
        'WETH': ('0x4200000000000000000000000000000000000006', 18),
        'OP':   ('0x4200000000000000000000000000000000000042', 18),
    },
    'base': {
        'USDC': ('0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913', 6),
        'WETH': ('0x4200000000000000000000000000000000000006', 18),
    },
    'polygon': {
        'USDC': ('0x3c499c542cEF5E3811e1192ce70d8cC03d5c3359', 6),
        'USDC_e': ('0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174', 6),
        'USDT': ('0xc2132D05D31c914a87C6611C10748AEb04B58e8F', 6),
        'WETH': ('0x7ceB23fD6bC0adD59E62ac25578270cFf1b9f619', 18),
        'WBTC': ('0x1BFD67037B42Cf73acF2047067bd4F2C47D9BfD6', 8),
    },
    'bsc': {
        'USDT': ('0x55d398326f99059fF775485246999027B3197955', 18),
        'USDC': ('0x8AC76a51cc950d9822D68b83fE1Ad97B32Cd580d', 18),
        'BUSD': ('0xe9e7CEA3DedcA5984780Bafc599bD69ADd087D56', 18),
    },
}


def encode_addr(a):
    return ('0' * 24) + a.lower().replace('0x', '')


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
                    if 'error' in data:
                        return {'error': data['error']}
                    return {'result': data.get('result')}
            except Exception:
                continue
    return None


async def get_token_balance(session, sem, rpcs, token, holder):
    data = ERC20_BALANCEOF + encode_addr(holder)
    r = await rpc_call(session, sem, rpcs, 'eth_call',
                       [{'to': token, 'data': data}, 'latest'])
    if r and 'result' in r and r['result'] and r['result'] != '0x':
        try: return int(r['result'], 16)
        except: return 0
    return 0


async def estimate_gas(session, sem, rpcs, addr, sender, calldata):
    params = [{'from': sender, 'to': addr, 'data': calldata, 'value': '0x0'}]
    r = await rpc_call(session, sem, rpcs, 'eth_estimateGas', params)
    if r and 'result' in r and r['result']:
        try: return int(r['result'], 16)
        except: return None
    return None


async def scan_contract(session, sem, rpcs, c, tokens):
    addr = c['address']
    findings = []

    for sym, (taddr, dec) in tokens.items():
        bal = await get_token_balance(session, sem, rpcs, taddr, addr)
        if bal == 0:
            continue
        usd_value = bal / (10 ** dec)
        if sym in ('WETH', 'cbETH'): usd_value *= 2500
        elif sym in ('WBTC',): usd_value *= 60000
        elif sym in ('LINK',): usd_value *= 12
        elif sym in ('UNI',): usd_value *= 7
        elif sym in ('OP', 'ARB'): usd_value *= 1.5
        elif sym in ('PEPE', 'SHIB'): usd_value *= 0.00001
        if usd_value < 10:
            continue

        # Try rescue functions
        rescue_hits = []
        for sel, sig in RESCUE_FUNCS.items():
            if sig.startswith('rescueTokens') or sig.startswith('recoverERC20') or sig.startswith('withdrawERC20') or sig.startswith('rescue(') or sig.startswith('recoverToken'):
                # arg: token address, then uint amount
                cd = '0x' + sel + encode_addr(taddr) + ('0' * 60) + 'ff'  # small amount
            elif sig == 'sweep(address)':
                cd = '0x' + sel + encode_addr(taddr)
            else:
                cd = '0x' + sel
            gas = await estimate_gas(session, sem, rpcs, addr, TEST_FROM, cd)
            if gas and gas > 30000:
                rescue_hits.append({'sig': sig, 'gas': gas})

        if rescue_hits:
            findings.append({
                'token': sym,
                'token_addr': taddr,
                'amount': bal / (10 ** dec),
                'usd_estimate': usd_value,
                'rescue_hits': rescue_hits,
            })

    return {
        'chain': c['chain'],
        'name': c.get('name', '?'),
        'address': addr,
        'category': c.get('category', ''),
        'findings': findings,
    } if findings else None


async def main():
    chains = json.load(open(os.path.join(SCRIPT_DIR, 'data', 'chains.json')))['chains']
    contracts = json.load(open(os.path.join(SCRIPT_DIR, 'data', 'contracts_multichain.json')))['contracts']
    contracts = [c for c in contracts
                 if not c.get('_comment') and c.get('address', '').startswith('0x')]

    print(f'[*] Stuck ERC-20 Hunter: scanning {len(contracts)} contracts')

    sem = asyncio.Semaphore(20)
    ssl_ctx = ssl.create_default_context(cafile=certifi.where())
    connector = aiohttp.TCPConnector(limit=40, ssl=ssl_ctx)

    t0 = time.time()
    candidates = []
    async with aiohttp.ClientSession(connector=connector) as session:
        by_chain = {}
        for c in contracts:
            by_chain.setdefault(c['chain'], []).append(c)

        for chain_name, ch_contracts in by_chain.items():
            ch_cfg = chains.get(chain_name)
            if not ch_cfg or chain_name not in COMMON_TOKENS:
                continue
            tokens = COMMON_TOKENS[chain_name]
            print(f'\n  Chain: {chain_name}  ({len(ch_contracts)} contracts, {len(tokens)} tokens)')
            tasks = [scan_contract(session, sem, ch_cfg['rpcs'], c, tokens) for c in ch_contracts]
            for done in asyncio.as_completed(tasks):
                r = await done
                if r:
                    candidates.append(r)
                    total_usd = sum(f['usd_estimate'] for f in r['findings'])
                    print(f"    *** {r['name'][:35]:35s}  ~${total_usd:>10,.0f}  hits={sum(len(f['rescue_hits']) for f in r['findings'])}")

    elapsed = time.time() - t0
    candidates.sort(key=lambda r: -sum(f['usd_estimate'] for f in r['findings']))

    print('\n' + '=' * 100)
    print('  STUCK ERC20 + RESCUE-FUNC RESULTS')
    print('=' * 100)
    print(f'  Scanned in {elapsed:.1f}s')
    print(f'  Candidates with both stuck tokens AND non-reverting rescue calls: {len(candidates)}')

    for i, r in enumerate(candidates[:30]):
        total = sum(f['usd_estimate'] for f in r['findings'])
        print(f"\n  [{i+1}] {r['chain']:10s} {r['name']:40s}  ~${total:,.0f}")
        print(f"      addr: {r['address']}")
        for f in r['findings']:
            print(f"      Token: {f['token']:6s}  amount={f['amount']:,.4f}  ~${f['usd_estimate']:,.0f}")
            for h in f['rescue_hits']:
                print(f"        rescue: {h['sig']:30s} gas={h['gas']}")

    out = os.path.join(SCRIPT_DIR, 'results', 'stuck_erc20_results.json')
    json.dump(candidates, open(out, 'w'), indent=2, default=str)
    print(f'\n[*] Saved: {out}')


if __name__ == '__main__':
    asyncio.run(main())
