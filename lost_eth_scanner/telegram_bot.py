#!/usr/bin/env python3
"""
TELEGRAM BOT
============
Lost ETH Scanner accessible via Telegram.

Setup:
  1. Talk to @BotFather on Telegram, create a bot, get a token
  2. export LOST_ETH_BOT_TOKEN=your_token_here
  3. python3 telegram_bot.py

Commands:
  /start           - Welcome message
  /help            - List commands
  /scan 0xAddr     - Scan an address for stuck balances
  /airdrops 0xAddr - Check airdrop holdings
  /nfts 0xAddr     - Check NFT holdings
  /stats           - Show database stats
  /watch 0xAddr    - Add address to monitor list
  /alerts          - Show recent alerts

Uses long-polling (no webhook required). Suitable for self-hosting.
Requires: pip install aiohttp
"""
import asyncio
import json
import os
import re
import ssl
import sys
import time

import aiohttp
import certifi

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from scanner_v2 import load_config, MultiRPC, scan_address
from storage_db import LostEthDB

TG_BASE = 'https://api.telegram.org/bot'
ADDRESS_RE = re.compile(r'0x[a-fA-F0-9]{40}')


class TelegramBot:
    def __init__(self, token):
        self.token = token
        self.api = TG_BASE + token
        self.offset = 0
        self.chains, self.contracts, self.tokens = load_config()
        self.db = LostEthDB()
        self.ssl_ctx = ssl.create_default_context(cafile=certifi.where())

    async def request(self, session, method, params=None):
        url = f'{self.api}/{method}'
        try:
            async with session.post(url, json=params or {},
                                     timeout=aiohttp.ClientTimeout(total=30)) as r:
                return await r.json()
        except Exception as e:
            return {'ok': False, 'error': str(e)}

    async def send(self, session, chat_id, text, parse_mode='Markdown'):
        await self.request(session, 'sendMessage', {
            'chat_id': chat_id,
            'text': text[:4000],  # Telegram message limit
            'parse_mode': parse_mode,
            'disable_web_page_preview': True,
        })

    def parse_address(self, text):
        m = ADDRESS_RE.search(text)
        return m.group(0) if m else None

    async def cmd_start(self, session, chat_id):
        msg = (
            "*Lost ETH Scanner Bot*\n\n"
            "Recover your forgotten ETH and tokens stuck in old contracts.\n\n"
            "*Commands:*\n"
            "/scan `0xAddr` - Full multi-chain scan\n"
            "/airdrops `0xAddr` - Check airdrop holdings\n"
            "/nfts `0xAddr` - Check NFT collection ownership\n"
            "/watch `0xAddr` - Add to monitoring list\n"
            "/stats - Show DB statistics\n"
            "/help - This message\n\n"
            "Made with care. All scans are read-only."
        )
        await self.send(session, chat_id, msg)

    async def cmd_scan(self, session, chat_id, address):
        await self.send(session, chat_id, f'Scanning `{address}` ...')
        sem = asyncio.Semaphore(80)
        async with aiohttp.ClientSession(
            connector=aiohttp.TCPConnector(limit=80, ssl=self.ssl_ctx)
        ) as s2:
            rpc = MultiRPC(self.chains, s2, sem)
            result = await scan_address(rpc, self.contracts, address, self.tokens, None, True)

        if result['total_findings'] == 0 and not result.get('native_findings'):
            await self.send(session, chat_id, f'No stuck balances found for `{address}`.')
            return

        lines = [f'*Findings for* `{address}`:\n']
        for ch, info in result.get('native_findings', {}).items():
            lines.append(f'`{ch:10s}` wallet: *{info["amount"]:.6f} {info["symbol"]}*')
        for ca, info in result['findings_per_contract'].items():
            for b in info['balances']:
                note = f' ({b.get("note","")})' if b.get('note') else ''
                lines.append(f'`{info["chain"]:10s}` *{info["name"][:25]}*: {b["amount"]:.6f} {b["symbol"]}{note}')
        await self.send(session, chat_id, '\n'.join(lines))

        # Save to DB
        self.db.add_address(address, label=f'TG user {chat_id}')

    async def cmd_airdrops(self, session, chat_id, address):
        from airdrop_checker import AIRDROPS, check_token_balance
        await self.send(session, chat_id, f'Checking airdrops for `{address}`...')
        async with aiohttp.ClientSession(
            connector=aiohttp.TCPConnector(limit=50, ssl=self.ssl_ctx)
        ) as s2:
            tasks = []
            valid = []
            for ad in AIRDROPS:
                if ad.get('chain') == 'solana' or not ad.get('token'):
                    continue
                rpcs = self.chains.get(ad['chain'], {}).get('rpcs', [])
                if not rpcs:
                    continue
                tasks.append(check_token_balance(s2, rpcs, ad['token'], address))
                valid.append(ad)
            results = await asyncio.gather(*tasks, return_exceptions=True)

        holdings = []
        for ad, bal in zip(valid, results):
            if isinstance(bal, Exception) or not bal:
                continue
            amount = bal / (10 ** ad['token_decimals'])
            holdings.append(f'*{ad["token_symbol"]}*: {amount:,.4f} ({ad["name"]})')

        if holdings:
            await self.send(session, chat_id, '*Airdrop holdings:*\n' + '\n'.join(holdings))
        else:
            await self.send(session, chat_id, 'No airdrop tokens detected.')

    async def cmd_nfts(self, session, chat_id, address):
        from nft_scanner import NFT_COLLECTIONS, check_erc721_balance
        await self.send(session, chat_id, f'Checking NFTs for `{address}`...')
        eth_rpcs = self.chains['ethereum']['rpcs']
        async with aiohttp.ClientSession(
            connector=aiohttp.TCPConnector(limit=80, ssl=self.ssl_ctx)
        ) as s2:
            tasks = [check_erc721_balance(s2, eth_rpcs, c['address'], address) for c in NFT_COLLECTIONS]
            counts = await asyncio.gather(*tasks, return_exceptions=True)

        holdings = []
        for col, count in zip(NFT_COLLECTIONS, counts):
            if isinstance(count, Exception) or not count:
                continue
            holdings.append(f'*{count}* x {col["name"]}')

        if holdings:
            await self.send(session, chat_id, '*NFT holdings:*\n' + '\n'.join(holdings))
        else:
            await self.send(session, chat_id, 'No NFTs from top collections detected.')

    async def cmd_stats(self, session, chat_id):
        chains, contracts, tokens = self.chains, self.contracts, self.tokens
        s = self.db.stats()
        msg = (
            "*Lost ETH DB Stats:*\n"
            f"- Chains: {len(chains)}\n"
            f"- Contracts: {len(contracts)}\n"
            f"- Tokens: {sum(len(t) for t in tokens.values())}\n\n"
            "*Local DB:*\n"
            f"- Tracked addresses: {s['addresses_tracked']}\n"
            f"- Total scans: {s['total_scans']}\n"
            f"- Total findings: {s['total_findings']}\n"
        )
        await self.send(session, chat_id, msg)

    async def cmd_watch(self, session, chat_id, address):
        self.db.add_address(address, label=f'TG-watch-{chat_id}')
        await self.send(session, chat_id, f'Added `{address}` to watch list.')

    async def handle_update(self, session, update):
        message = update.get('message')
        if not message:
            return
        chat_id = message['chat']['id']
        text = message.get('text', '').strip()

        if text.startswith('/start') or text.startswith('/help'):
            await self.cmd_start(session, chat_id)
        elif text.startswith('/scan'):
            addr = self.parse_address(text)
            if addr:
                await self.cmd_scan(session, chat_id, addr)
            else:
                await self.send(session, chat_id, 'Usage: `/scan 0xYourAddress`')
        elif text.startswith('/airdrops'):
            addr = self.parse_address(text)
            if addr:
                await self.cmd_airdrops(session, chat_id, addr)
            else:
                await self.send(session, chat_id, 'Usage: `/airdrops 0xYourAddress`')
        elif text.startswith('/nfts'):
            addr = self.parse_address(text)
            if addr:
                await self.cmd_nfts(session, chat_id, addr)
            else:
                await self.send(session, chat_id, 'Usage: `/nfts 0xYourAddress`')
        elif text.startswith('/stats'):
            await self.cmd_stats(session, chat_id)
        elif text.startswith('/watch'):
            addr = self.parse_address(text)
            if addr:
                await self.cmd_watch(session, chat_id, addr)
            else:
                await self.send(session, chat_id, 'Usage: `/watch 0xYourAddress`')
        elif self.parse_address(text):
            # Bare address - default to scan
            await self.cmd_scan(session, chat_id, self.parse_address(text))
        else:
            await self.send(session, chat_id, "Unknown command. Type /help for commands.")

    async def run(self):
        print(f'Bot running with token {self.token[:10]}...')
        async with aiohttp.ClientSession(
            connector=aiohttp.TCPConnector(ssl=self.ssl_ctx)
        ) as session:
            while True:
                resp = await self.request(session, 'getUpdates', {
                    'offset': self.offset, 'timeout': 25
                })
                if not resp.get('ok'):
                    await asyncio.sleep(5)
                    continue
                for update in resp.get('result', []):
                    self.offset = update['update_id'] + 1
                    try:
                        await self.handle_update(session, update)
                    except Exception as e:
                        print(f'Error handling update: {e}')


def main():
    token = os.environ.get('LOST_ETH_BOT_TOKEN')
    if not token:
        print('Set LOST_ETH_BOT_TOKEN env var')
        print('Get a token from @BotFather on Telegram')
        return
    bot = TelegramBot(token)
    asyncio.run(bot.run())


if __name__ == '__main__':
    main()
