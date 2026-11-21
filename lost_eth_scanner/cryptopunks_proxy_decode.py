#!/usr/bin/env python3
"""
Decode the mysterious proxy contracts holding CryptoPunks pendingWithdrawals.
"""
import asyncio
import json
import os
import ssl
import urllib.request
import certifi

import aiohttp

OPCODES = {
    0x00:'STOP',0x01:'ADD',0x02:'MUL',0x03:'SUB',0x04:'DIV',
    0x14:'EQ',0x15:'ISZERO',0x16:'AND',0x17:'OR',
    0x20:'KECCAK256',
    0x30:'ADDRESS',0x31:'BALANCE',0x32:'ORIGIN',0x33:'CALLER',0x34:'CALLVALUE',
    0x35:'CALLDATALOAD',0x36:'CALLDATASIZE',0x37:'CALLDATACOPY',0x38:'CODESIZE',
    0x39:'CODECOPY',
    0x3d:'RETURNDATASIZE',0x3e:'RETURNDATACOPY',
    0x50:'POP',0x51:'MLOAD',0x52:'MSTORE',0x53:'MSTORE8',0x54:'SLOAD',0x55:'SSTORE',
    0x56:'JUMP',0x57:'JUMPI',0x5b:'JUMPDEST',
    0xf1:'CALL',0xf2:'CALLCODE',0xf3:'RETURN',0xf4:'DELEGATECALL',
    0xfa:'STATICCALL',0xfd:'REVERT',0xfe:'INVALID',0xff:'SELFDESTRUCT',
}
for i in range(32):
    OPCODES[0x60 + i] = f'PUSH{i+1}'
for i in range(16):
    OPCODES[0x80 + i] = f'DUP{i+1}'
    OPCODES[0x90 + i] = f'SWAP{i+1}'


def disasm(code: bytes):
    out = []
    i = 0
    while i < len(code):
        op = code[i]
        name = OPCODES.get(op, f'?{op:02x}')
        if 0x60 <= op <= 0x7f:
            push_len = op - 0x5f
            data = code[i + 1:i + 1 + push_len]
            out.append((i, name, data.hex()))
            i += 1 + push_len
        else:
            out.append((i, name, ''))
            i += 1
    return out


async def get_code(addr):
    payload = {'jsonrpc': '2.0', 'method': 'eth_getCode', 'params': [addr, 'latest'], 'id': 1}
    ctx = ssl.create_default_context(cafile=certifi.where())
    async with aiohttp.ClientSession(connector=aiohttp.TCPConnector(ssl=ctx)) as s:
        async with s.post('https://ethereum-rpc.publicnode.com', json=payload, timeout=aiohttp.ClientTimeout(total=15)) as r:
            d = await r.json()
            return d.get('result', '0x')


async def main():
    addrs = [
        ('0xcafbf7952763c7237d2848a553e3146cbdd08602', '#1: 103.35 ETH proxy'),
        ('0x47452c970e08bf7105c753b798536e685e042231', '#2: 28.89 ETH proxy'),
        ('0x3bb0fe1d19e1f10a457cd3d26cd0db78dfdd677e', '#3: 0.8 ETH micro-contract'),
    ]
    for addr, desc in addrs:
        print(f'\n{"=" * 70}')
        print(f'  {desc}')
        print(f'  {addr}')
        print('=' * 70)

        code_hex = await get_code(addr)
        if not code_hex or code_hex == '0x':
            print('  No code')
            continue
        code = bytes.fromhex(code_hex[2:])
        print(f'  Bytecode ({len(code)} bytes):')
        print(f'  {code_hex}')
        print(f'\n  Disassembly:')
        for pc, name, data in disasm(code):
            line = f'    {pc:>4x}: {name}'
            if data:
                line += f' 0x{data}'
                # Try interpret as address
                if len(data) == 40:
                    line += f'  -> 0x{data}'
            print(line)


if __name__ == '__main__':
    asyncio.run(main())
