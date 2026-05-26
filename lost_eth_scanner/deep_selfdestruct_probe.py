#!/usr/bin/env python3
"""
Deep dive on contracts with SELFDESTRUCT + balance.
Examines bytecode around SELFDESTRUCT sites and probes the kill functions.
"""
import asyncio
import json
import os
import ssl

import aiohttp
import certifi

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))


def disasm(code: bytes):
    i = 0
    while i < len(code):
        op = code[i]
        if 0x60 <= op <= 0x7f:
            push_len = op - 0x5f
            data = code[i + 1:i + 1 + push_len]
            yield i, op, data
            i += 1 + push_len
        else:
            yield i, op, None
            i += 1


OP_NAMES = {
    0x00: 'STOP', 0x01: 'ADD', 0x02: 'MUL', 0x03: 'SUB', 0x04: 'DIV',
    0x14: 'EQ', 0x15: 'ISZERO', 0x16: 'AND', 0x17: 'OR',
    0x20: 'KECCAK256',
    0x30: 'ADDRESS', 0x31: 'BALANCE', 0x32: 'ORIGIN', 0x33: 'CALLER',
    0x34: 'CALLVALUE', 0x35: 'CALLDATALOAD', 0x36: 'CALLDATASIZE',
    0x50: 'POP', 0x51: 'MLOAD', 0x52: 'MSTORE', 0x54: 'SLOAD', 0x55: 'SSTORE',
    0x56: 'JUMP', 0x57: 'JUMPI', 0x58: 'PC', 0x5b: 'JUMPDEST',
    0xf1: 'CALL', 0xf3: 'RETURN', 0xf4: 'DELEGATECALL', 0xfd: 'REVERT',
    0xff: 'SELFDESTRUCT',
}
for i in range(32):
    OP_NAMES[0x60 + i] = f'PUSH{i+1}'
for i in range(16):
    OP_NAMES[0x80 + i] = f'DUP{i+1}'
    OP_NAMES[0x90 + i] = f'SWAP{i+1}'


def disasm_text(code: bytes, start: int, length: int):
    """Return disasm of `length` instructions starting BEFORE position `start`."""
    instrs = list(disasm(code))
    target_idx = None
    for i, (pc, op, data) in enumerate(instrs):
        if pc >= start:
            target_idx = i
            break
    if target_idx is None:
        return []
    out = []
    for i in range(max(0, target_idx - length), min(len(instrs), target_idx + 5)):
        pc, op, data = instrs[i]
        name = OP_NAMES.get(op, f'?{op:02x}')
        marker = '<--HERE' if pc == start else ''
        if data:
            out.append(f"  {pc:>5x}: {name:<10} 0x{data.hex()} {marker}")
        else:
            out.append(f"  {pc:>5x}: {name} {marker}")
    return out


async def rpc_call(rpc, method, params, timeout=15.0):
    payload = {'jsonrpc': '2.0', 'method': method, 'params': params, 'id': 1}
    ctx = ssl.create_default_context(cafile=certifi.where())
    async with aiohttp.ClientSession(connector=aiohttp.TCPConnector(ssl=ctx)) as s:
        try:
            async with s.post(rpc, json=payload,
                             timeout=aiohttp.ClientTimeout(total=timeout)) as r:
                d = await r.json()
                return d
        except Exception as e:
            return {'error': str(e)}


# Targets with balance + SELFDESTRUCT
TARGETS = [
    ('zksync', '0x8B791913eB07C32779a16750e3868aA8495F5964', 'Mute.io Router (7.17 ETH)'),
    ('celo', '0xE3D8bd6Aed4F159bc8000a9cD47CffDb95F96121', 'Ubeswap V1 (12.17 CELO)'),
    ('ethereum', '0xB21f8684f23Dbb1008508B4DE91a0aaEDEbdB7E4', 'Etheria v1.0 (0.0001 ETH)'),
]


async def main():
    chains = json.load(open(os.path.join(SCRIPT_DIR, 'data', 'chains.json')))['chains']

    for chain, addr, label in TARGETS:
        print(f'\n{"="*90}')
        print(f'  {label}')
        print(f'  chain={chain}  addr={addr}')
        print('=' * 90)

        for rpc in chains[chain]['rpcs']:
            print(f'\n  RPC: {rpc}')
            r = await rpc_call(rpc, 'eth_getCode', [addr, 'latest'])
            if not r or 'result' not in r:
                continue
            code_hex = r['result']
            if not code_hex or code_hex == '0x':
                print('    EOA or no code')
                continue

            try:
                code = bytes.fromhex(code_hex[2:])
            except ValueError:
                continue

            print(f'  Code size: {len(code)} bytes')

            # Find SELFDESTRUCTs
            instrs = list(disasm(code))
            sd_pcs = [pc for pc, op, _ in instrs if op == 0xff]
            print(f'  SELFDESTRUCT sites: {len(sd_pcs)} at PCs {[hex(p) for p in sd_pcs]}')

            for sd_pc in sd_pcs[:3]:
                print(f'\n  Disassembly around SELFDESTRUCT at PC {sd_pc:x}:')
                for line in disasm_text(code, sd_pc, 25):
                    print(line)

            # Check balance
            bal_r = await rpc_call(rpc, 'eth_getBalance', [addr, 'latest'])
            if bal_r and 'result' in bal_r:
                bal = int(bal_r['result'], 16)
                print(f'\n  Current balance: {bal/1e18:,.6f} native')

            # Try calling kill() / destruct() / etc and report estimateGas
            print(f'\n  Probing kill functions (eth_estimateGas from random EOA):')
            test_from = '0xCafeBabeCafeBabeCafeBabeCafeBabeCafeBabe'
            for sel, name in [
                ('41c0e1b5', 'kill()'),
                ('35f46994', 'destroy()'),
                ('9cb8a26a', 'destruct()'),
                ('5e80fe79', 'suicide()'),
                ('cb3e64fd', 'shutdown()'),
                ('00f55d9d', 'destroy(address)'),
            ]:
                cd = '0x' + sel
                if name == 'destroy(address)':
                    cd += '0' * 24 + test_from[2:].lower()
                est = await rpc_call(rpc, 'eth_estimateGas',
                                     [{'from': test_from, 'to': addr, 'data': cd, 'value': '0x0'}])
                if est and 'result' in est and est['result']:
                    try:
                        g = int(est['result'], 16)
                        if g > 30000:
                            print(f'    *** {name:25s} gas={g:>8} - HIGH! Investigate!')
                        else:
                            print(f'    {name:25s} gas={g}')
                    except Exception:
                        print(f'    {name:25s} {est}')
                elif est and 'error' in est:
                    err = est['error']
                    if isinstance(err, dict):
                        msg = err.get('message', '')[:60]
                    else:
                        msg = str(err)[:60]
                    if 'revert' not in msg.lower():
                        print(f'    {name:25s} ERROR: {msg}')
            break


if __name__ == '__main__':
    asyncio.run(main())
