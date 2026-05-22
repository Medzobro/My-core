#!/usr/bin/env python3
"""
LOST ETH WITHDRAW HELPER
========================
Generates the EXACT raw call data you need to withdraw your stuck funds.
You then sign and send the transaction yourself via MetaMask, MyEtherWallet,
hardware wallet, or any signer you control.

WE NEVER ASK FOR YOUR PRIVATE KEY. EVER. YOU SIGN THE TRANSACTION YOURSELF.

Usage:
    python3 withdraw_helper.py <contract_address> <token_address> <amount_wei>

Example (withdraw all ETH from IDEX 1.0):
    python3 withdraw_helper.py \\
        0x2a0c0DBEcC7E4D658f48E01e3fA353F44050c208 \\
        0x0000000000000000000000000000000000000000 \\
        12345678901234567890
"""

import sys


def encode_uint256(n):
    return f'{n:064x}'


def encode_address(a):
    return '0' * 24 + a.lower().replace('0x', '')


def main():
    if len(sys.argv) < 4:
        print(__doc__)
        sys.exit(1)

    contract = sys.argv[1]
    token = sys.argv[2]
    amount_wei = int(sys.argv[3])

    # withdraw(address,uint256) selector = 0xf3fef3a3
    # used by IDEX, Token.Store, Saturn Network, and most EtherDelta-forks
    selector = 'f3fef3a3'
    data = '0x' + selector + encode_address(token) + encode_uint256(amount_wei)

    print()
    print('=' * 72)
    print('  WITHDRAW TRANSACTION DATA')
    print('=' * 72)
    print(f'  TO:        {contract}')
    print(f'  VALUE:     0 ETH (you do not SEND, you RECEIVE)')
    print(f'  GAS LIMIT: 100000  (recommended)')
    print(f'  DATA:      {data}')
    print()
    print('-' * 72)
    print('  HOW TO USE')
    print('-' * 72)
    print('  Option 1) MetaMask:')
    print('     - Click "Send"')
    print(f'     - To: {contract}')
    print('     - Click "Hex" tab and paste DATA above')
    print('     - Confirm and sign')
    print()
    print('  Option 2) MyEtherWallet (MEW) Offline:')
    print('     - Send Offline > Generate Information')
    print(f'     - To Address: {contract}')
    print('     - Amount: 0')
    print('     - Gas: 100000')
    print(f'     - Data: {data}')
    print('     - Sign with your private key on offline computer')
    print()
    print('  Option 3) Etherscan Write Contract:')
    print(f'     https://etherscan.io/address/{contract}#writeContract')
    print('     - Connect Wallet')
    print('     - Find "withdraw" function')
    print(f'     - token: {token}')
    print(f'     - amount: {amount_wei}')
    print('     - Click Write and Sign')
    print()
    print('  Option 4) Foundry/cast:')
    print(f'     cast send {contract} "withdraw(address,uint256)" {token} {amount_wei}')
    print()
    print('-' * 72)
    print('  SAFETY CHECKLIST')
    print('-' * 72)
    print(f'  [ ] Verify contract address: {contract}')
    print('  [ ] Use small test amount first if amount > 1 ETH')
    print('  [ ] Wait 240 blocks (~1 hour) since last interaction with the contract')
    print('  [ ] Never share your private key/seed with anyone')
    print('  [ ] Verify you copied the DATA exactly (no extra spaces)')
    print('=' * 72)


if __name__ == '__main__':
    main()
