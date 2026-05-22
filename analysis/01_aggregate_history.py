#!/usr/bin/env python3
"""
Stage 1: Aggregate FULL event history of the Exchange contract.
Walks every block from creation to latest in chunks, captures all events.
"""
import requests, json, time, os, sys
from collections import defaultdict

ADDR = '0x2a0c0dbecc7e4d658f48e01e3fa353f44050c208'
CREATION_BLOCK = 4317141
RPCS = [
    'https://ethereum-rpc.publicnode.com',
    'https://eth.llamarpc.com',
    'https://rpc.ankr.com/eth',
    'https://cloudflare-eth.com',
]
OUT_DIR = os.path.dirname(os.path.abspath(__file__))

# Event topic0 hashes
TOPICS = {
    '0xdcbc1c05240f31ff3ad067ef1ee35ce4997762752e3a095284754544f4c709d7': 'Deposit',
    '0xf341246adaac6f497bc2a656f546ab9e182111d630394f0c57c710a59a2cb567': 'Withdraw',
    '0x6effdda786735d5033bfad5f53e5131abcced9e52be6c507b62d639685fbed6d': 'Trade',
    '0xcd0366dce5247d874ffc60a762aa7abbb82c1695bbb171609c1b8861e279eb73': 'SetOwner',  # SetOwner(address,address) indexed
}

def call(method, params, retries=3):
    err = None
    for rpc in RPCS:
        for _ in range(retries):
            try:
                r = requests.post(rpc, json={'jsonrpc':'2.0','method':method,'params':params,'id':1}, timeout=30)
                d = r.json()
                if 'result' in d:
                    return d['result']
                err = d.get('error')
            except Exception as e:
                err = str(e)
                time.sleep(0.5)
    raise RuntimeError(f'RPC failed: {err}')

def main():
    latest = int(call('eth_blockNumber', []), 16)
    print(f'Latest block: {latest:,}')
    print(f'Creation block: {CREATION_BLOCK:,}')
    print(f'Total span: {latest - CREATION_BLOCK:,} blocks')

    deposits = []
    withdraws = []
    trades = []
    setowners = []
    other = defaultdict(int)

    chunk = 200_000
    start = CREATION_BLOCK
    block = start
    total_logs = 0
    t0 = time.time()
    while block <= latest:
        end = min(block + chunk - 1, latest)
        try:
            logs = call('eth_getLogs', [{
                'address': ADDR,
                'fromBlock': hex(block),
                'toBlock': hex(end),
            }])
        except Exception as e:
            # narrow chunk
            if chunk > 10000:
                chunk = chunk // 2
                print(f'  shrinking chunk to {chunk}')
                continue
            else:
                print(f'  ERR at {block}: {e}')
                block = end + 1
                continue
        for log in logs or []:
            t0_topic = log['topics'][0] if log.get('topics') else None
            blk = int(log['blockNumber'], 16)
            if t0_topic in TOPICS:
                name = TOPICS[t0_topic]
                if name == 'Deposit':
                    # Deposit(address token, address user, uint256 amount, uint256 balance) - non-indexed
                    data = log['data'][2:]
                    token   = '0x' + data[24:64]
                    user    = '0x' + data[64+24:128]
                    amount  = int(data[128:192], 16)
                    balance = int(data[192:256], 16)
                    deposits.append((blk, token, user, amount, balance, log['transactionHash']))
                elif name == 'Withdraw':
                    data = log['data'][2:]
                    token   = '0x' + data[24:64]
                    user    = '0x' + data[64+24:128]
                    amount  = int(data[128:192], 16)
                    balance = int(data[192:256], 16)
                    withdraws.append((blk, token, user, amount, balance, log['transactionHash']))
                elif name == 'Trade':
                    # Trade(address tokenBuy, uint256 amountBuy, address tokenSell, uint256 amountSell, address get, address give)
                    data = log['data'][2:]
                    tokenBuy   = '0x' + data[24:64]
                    amountBuy  = int(data[64:128], 16)
                    tokenSell  = '0x' + data[128+24:192]
                    amountSell = int(data[192:256], 16)
                    getAddr    = '0x' + data[256+24:320]
                    giveAddr   = '0x' + data[320+24:384]
                    trades.append((blk, tokenBuy, amountBuy, tokenSell, amountSell, getAddr, giveAddr, log['transactionHash']))
                elif name == 'SetOwner':
                    prev = '0x' + log['topics'][1][26:]
                    new  = '0x' + log['topics'][2][26:]
                    setowners.append((blk, prev, new, log['transactionHash']))
            else:
                other[t0_topic] += 1
        total_logs += len(logs or [])
        elapsed = time.time() - t0
        progress = (block - start) / (latest - start) * 100
        rate = total_logs / max(elapsed, 0.001)
        print(f'  blocks {block:>10,} -> {end:>10,} | logs {total_logs:>7,} | {progress:5.1f}% | {elapsed:5.0f}s | {rate:.0f} logs/s')
        block = end + 1

    print('\n=== Summary ===')
    print(f'Total events captured: {len(deposits) + len(withdraws) + len(trades) + len(setowners)}')
    print(f'  Deposits:    {len(deposits):,}')
    print(f'  Withdraws:   {len(withdraws):,}')
    print(f'  Trades:      {len(trades):,}')
    print(f'  SetOwner:    {len(setowners):,}')
    print(f'  Other topics: {sum(other.values()):,}')

    # Save raw data
    with open(f'{OUT_DIR}/deposits.json', 'w') as f:
        json.dump(deposits, f)
    with open(f'{OUT_DIR}/withdraws.json', 'w') as f:
        json.dump(withdraws, f)
    with open(f'{OUT_DIR}/trades.json', 'w') as f:
        json.dump(trades, f)
    with open(f'{OUT_DIR}/setowners.json', 'w') as f:
        json.dump(setowners, f)

    # Setowner history
    print('\n=== Owner change history ===')
    for blk, prev, new, tx in setowners:
        print(f'  block {blk:,}: {prev} -> {new}')

if __name__ == '__main__':
    main()
