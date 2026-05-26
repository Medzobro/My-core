#!/usr/bin/env python3
"""
EVM BYTECODE DISASSEMBLER + STATIC SECURITY ANALYZER
======================================================
For a target contract:
  1. Locate the dispatcher jump for a given selector (e.g. withdraw).
  2. Disassemble the function body up to its STOP/REVERT/RETURN.
  3. Check whether the function:
     - Reads msg.sender (CALLER opcode 0x33)
     - Hashes msg.sender into a storage slot (KECCAK256 after CALLER)
     - Performs SLOAD from that slot (state-gated)
     - Performs CALL with VALUE from contract balance
  4. Verdict:
     - GATED: function reads msg.sender state before paying out -> needs your address to have state
     - PUBLIC_DRAIN: pays msg.sender from contract balance without msg.sender-keyed SLOAD
     - NO_PAY: does not transfer ETH at all
"""
import json, sys, os
import urllib.request, ssl, certifi

OPCODES = {
    0x00:'STOP',0x01:'ADD',0x02:'MUL',0x03:'SUB',0x04:'DIV',0x05:'SDIV',0x06:'MOD',0x07:'SMOD',
    0x08:'ADDMOD',0x09:'MULMOD',0x0a:'EXP',0x0b:'SIGNEXTEND',
    0x10:'LT',0x11:'GT',0x12:'SLT',0x13:'SGT',0x14:'EQ',0x15:'ISZERO',
    0x16:'AND',0x17:'OR',0x18:'XOR',0x19:'NOT',0x1a:'BYTE',0x1b:'SHL',0x1c:'SHR',0x1d:'SAR',
    0x20:'KECCAK256',
    0x30:'ADDRESS',0x31:'BALANCE',0x32:'ORIGIN',0x33:'CALLER',0x34:'CALLVALUE',
    0x35:'CALLDATALOAD',0x36:'CALLDATASIZE',0x37:'CALLDATACOPY',0x38:'CODESIZE',
    0x39:'CODECOPY',0x3a:'GASPRICE',0x3b:'EXTCODESIZE',0x3c:'EXTCODECOPY',0x3d:'RETURNDATASIZE',
    0x3e:'RETURNDATACOPY',0x3f:'EXTCODEHASH',
    0x40:'BLOCKHASH',0x41:'COINBASE',0x42:'TIMESTAMP',0x43:'NUMBER',0x44:'DIFFICULTY',
    0x45:'GASLIMIT',0x46:'CHAINID',0x47:'SELFBALANCE',0x48:'BASEFEE',
    0x50:'POP',0x51:'MLOAD',0x52:'MSTORE',0x53:'MSTORE8',0x54:'SLOAD',0x55:'SSTORE',
    0x56:'JUMP',0x57:'JUMPI',0x58:'PC',0x59:'MSIZE',0x5a:'GAS',0x5b:'JUMPDEST',
    0xa0:'LOG0',0xa1:'LOG1',0xa2:'LOG2',0xa3:'LOG3',0xa4:'LOG4',
    0xf0:'CREATE',0xf1:'CALL',0xf2:'CALLCODE',0xf3:'RETURN',0xf4:'DELEGATECALL',
    0xf5:'CREATE2',0xfa:'STATICCALL',0xfd:'REVERT',0xfe:'INVALID',0xff:'SELFDESTRUCT',
}
for i in range(32):
    OPCODES[0x60 + i] = f'PUSH{i+1}'
for i in range(16):
    OPCODES[0x80 + i] = f'DUP{i+1}'
    OPCODES[0x90 + i] = f'SWAP{i+1}'


def disasm(code: bytes, start=0, end=None):
    if end is None:
        end = len(code)
    instrs = []
    i = start
    while i < end:
        op = code[i]
        name = OPCODES.get(op, f'UNK_{op:02x}')
        if 0x60 <= op <= 0x7f:
            push_len = op - 0x5f
            data = code[i + 1:i + 1 + push_len]
            instrs.append((i, name, data.hex()))
            i += 1 + push_len
        else:
            instrs.append((i, name, ''))
            i += 1
    return instrs


def find_selector_jump(instrs, selector_hex):
    """Find the JUMPI that dispatches to selector_hex (8 hex chars)."""
    target_int = int(selector_hex, 16)
    # Common pattern: PUSH4 selector, EQ, PUSH2 dest, JUMPI
    for idx, (pc, name, data) in enumerate(instrs):
        if name == 'PUSH4' and data and int(data, 16) == target_int:
            # Look ahead for EQ then PUSH2/PUSH4 then JUMPI
            for j in range(idx + 1, min(idx + 8, len(instrs))):
                _, n2, d2 = instrs[j]
                if n2 in ('PUSH1','PUSH2','PUSH3','PUSH4') and d2:
                    try:
                        dest = int(d2, 16)
                    except ValueError:
                        continue
                    if j + 1 < len(instrs) and instrs[j + 1][1] == 'JUMPI':
                        return dest
    return None


def analyze_function_body(instrs, jumpdest):
    """From a JUMPDEST PC, walk instructions and check security properties."""
    # Find the index of the JUMPDEST
    start_idx = None
    for idx, (pc, name, _) in enumerate(instrs):
        if pc == jumpdest and name == 'JUMPDEST':
            start_idx = idx
            break
    if start_idx is None:
        return {'error': 'jumpdest not found'}

    # Walk forward, collecting opcodes until we hit STOP/REVERT/RETURN/INVALID
    # (or follow JUMPs - simplified, we won't follow them here)
    saw_caller = False
    saw_keccak_after_caller = False
    saw_sload = False
    sload_slot_pushed = []  # value pushed before SLOAD (small int = global slot, otherwise computed)
    saw_call_value = False
    saw_revert_after_eq = False
    saw_selfdestruct = False
    has_owner_check = False

    last_few = []  # rolling window for context
    caller_recent = False
    keccak_recent = False
    sload_pending_const = None

    for idx in range(start_idx, min(start_idx + 600, len(instrs))):
        pc, name, data = instrs[idx]
        last_few.append(name)
        if len(last_few) > 6:
            last_few.pop(0)

        if name == 'CALLER':
            saw_caller = True
            caller_recent = True
        elif name == 'KECCAK256' and caller_recent:
            saw_keccak_after_caller = True
            keccak_recent = True
            caller_recent = False
        elif name == 'SLOAD':
            saw_sload = True
            if keccak_recent:
                # state-gated lookup mapping[caller]
                pass
            keccak_recent = False
        elif name == 'CALL':
            saw_call_value = True
        elif name == 'SELFDESTRUCT':
            saw_selfdestruct = True

        # owner() check pattern: SLOAD slot 0, EQ CALLER (or vice versa), ISZERO, JUMPI -> revert
        # Heuristic: if we see CALLER followed by EQ + ISZERO (typical onlyOwner)
        window = last_few[-4:]
        if 'CALLER' in window and 'EQ' in window and 'ISZERO' in window:
            has_owner_check = True
        if 'SLOAD' in window and 'CALLER' in window and 'EQ' in window:
            has_owner_check = True

        if name in ('STOP', 'RETURN', 'REVERT', 'INVALID'):
            break

    return {
        'reads_caller': saw_caller,
        'hashes_caller_for_storage_key': saw_keccak_after_caller,
        'reads_storage': saw_sload,
        'transfers_value': saw_call_value,
        'self_destructs': saw_selfdestruct,
        'has_owner_check': has_owner_check,
    }


def fetch_code(rpc, addr):
    body = json.dumps({
        'jsonrpc': '2.0', 'method': 'eth_getCode', 'params': [addr, 'latest'], 'id': 1
    }).encode()
    req = urllib.request.Request(rpc, data=body, headers={
        'Content-Type': 'application/json',
        'User-Agent': 'Mozilla/5.0 (compatible; bytecode-analyzer/1.0)',
        'Accept': 'application/json',
    })
    ctx = ssl.create_default_context(cafile=certifi.where())
    with urllib.request.urlopen(req, timeout=15, context=ctx) as resp:
        d = json.loads(resp.read())
        return d.get('result', '0x')


def fetch_code_with_fallback(rpcs, addr):
    last_err = None
    for rpc in rpcs:
        try:
            return fetch_code(rpc, addr)
        except Exception as e:
            last_err = e
            continue
    raise last_err


def verdict(props):
    if not props.get('transfers_value'):
        return 'NO_PAY (function does not transfer ETH)'
    if props.get('has_owner_check'):
        return 'OWNER_GATED (only owner can call)'
    if props.get('hashes_caller_for_storage_key') and props.get('reads_storage'):
        return 'USER_STATE_GATED (drains caller-keyed mapping; need pre-existing balance)'
    if props.get('reads_caller'):
        return 'CALLER_LOGGED (uses CALLER but no obvious mapping read; needs deeper trace)'
    return 'POTENTIALLY_PUBLIC_DRAIN (no caller-keyed guard detected!)'


# Default candidates - high-score from deep_audit
DEFAULT_TARGETS = [
    ('ethereum', 'PoWH3D', '0xB3775fB83F7D12A36E0475aBdD1FCA35c091efBe',
     ['3ccfd60b']),
    ('ethereum', 'WithdrawDAO', '0xbf4ed7b27f1d666546e30d74d50d173d20bca754',
     ['3ccfd60b']),
    ('ethereum', 'CryptoPunks Marketplace', '0xb47e3cd837dDF8e4c57F05d70Ab865de6e193BBB',
     ['3ccfd60b']),
    ('ethereum', 'CryptoPunks (old contract)', '0x6BA6f2207e343923BA692e5Cae646Fb0F566DB8D',
     ['3ccfd60b']),
    ('ethereum', 'Augur v1 Cash', '0xd5524179cB7AE012f5B642C1D6D700Bbaa76B96b',
     ['3ccfd60b', '2e1a7d4d']),
    ('ethereum', 'DigixDAO', '0xE0B7927c4aF23765Cb51314A0E0521A9645F0E2A',
     ['3ccfd60b']),
    ('ethereum', 'Babbage Compound (cETH)', '0x4Ddc2D193948926D02f9B1fE9e1daa0718270ED5',
     ['3ccfd60b']),
    ('ethereum', 'Curve Old Pool stETH', '0xDC24316b9AE028F1497c275EB9192a3Ea0f67022',
     ['3ccfd60b']),
    ('ethereum', 'Hop Bridge L1 ETH (old)', '0xb8901acB165ed027E32754E0FFe830802919727f',
     ['3ccfd60b']),
    ('ethereum', 'Tornado Cash 100 ETH', '0xA160cdAB225685dA1d56aa342Ad8841c3b53f291',
     ['3ccfd60b']),
    ('base', 'Friend.tech', '0xCF205808Ed36593aa40a44F10c7f7C2F67d4A4d4',
     ['3ccfd60b']),
    ('moonbeam', 'Beamswap', '0x96b244391D98B62D19aE89b1A4dCcf0fc56970C7',
     ['3ccfd60b']),
    ('polygon', 'QiDao Old', '0xa3Fa99A148fA48D14Ed51d610c367C61876997F1',
     ['3ccfd60b']),
    ('zksync', 'Mute.io Router', '0x8B791913eB07C32779a16750e3868aA8495F5964',
     ['3ccfd60b']),
    ('celo', 'Ubeswap Router V1', '0xE3D8bd6Aed4F159bc8000a9cD47CffDb95F96121',
     ['3ccfd60b']),
    ('ethereum', 'Etheria v1.0', '0xB21f8684f23Dbb1008508B4DE91a0aaEDEbdB7E4',
     ['3ccfd60b']),
]


def main():
    chains = json.load(open(os.path.join(os.path.dirname(__file__), 'data', 'chains.json')))['chains']
    print('=' * 90)
    print('  STATIC ANALYSIS OF withdraw() / claim() / drain functions')
    print('=' * 90)

    for chain, name, addr, selectors in DEFAULT_TARGETS:
        rpcs = chains[chain]['rpcs']
        try:
            code_hex = fetch_code_with_fallback(rpcs, addr)
        except Exception as e:
            print(f'\n[{name}] failed to fetch code: {e}')
            continue
        if not code_hex or code_hex == '0x':
            print(f'\n[{name}] EOA, skipping')
            continue
        code = bytes.fromhex(code_hex[2:])
        instrs = disasm(code)
        print(f'\n┌─────────────────────────────────────────────────────────────')
        print(f'│ {chain}  {name}')
        print(f'│ {addr}   ({len(code)} bytes, {len(instrs)} instrs)')
        print(f'└─────────────────────────────────────────────────────────────')

        for sel in selectors:
            jd = find_selector_jump(instrs, sel)
            if jd is None:
                print(f'    [{sel}]   selector not found in dispatcher')
                continue
            props = analyze_function_body(instrs, jd)
            v = verdict(props)
            print(f'    [{sel}]   jumpdest=0x{jd:x}')
            print(f'       reads_caller             : {props.get("reads_caller")}')
            print(f'       hashes_caller_for_slot   : {props.get("hashes_caller_for_storage_key")}')
            print(f'       reads_storage            : {props.get("reads_storage")}')
            print(f'       transfers_value (CALL)   : {props.get("transfers_value")}')
            print(f'       has_owner_check          : {props.get("has_owner_check")}')
            print(f'       self_destructs           : {props.get("self_destructs")}')
            print(f'       VERDICT                  : {v}')


if __name__ == '__main__':
    main()
