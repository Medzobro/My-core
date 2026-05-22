# Lost ETH Scanner Suite

> Production-grade toolkit for discovering and recovering forgotten Ethereum funds across mainnet and Layer 2 networks.

## Overview

The Lost ETH Scanner is a comprehensive multi-chain async toolkit that helps you:

- **Find** stuck balances in 100+ known forgotten contracts (DEXs, lending pools, bridges)
- **Discover** unknown contracts your address has interacted with via tx history
- **Check** airdrop holdings across 20+ historical airdrops
- **Detect** NFT ownership across 33 top collections
- **Monitor** addresses continuously with diff-based alerts
- **Generate** raw transaction data for safe offline signing
- **Analyze** any contract's bytecode forensically

## Quick Start

### Install
```bash
git clone https://github.com/Medzobro/My-core
cd My-core/lost_eth_scanner
git checkout analysis/idex-1.0-full-report
pip install -r requirements.txt
```

### One-shot scan
```bash
python3 lost_eth.py scan 0xYourAddress --include-native
```

### Full discovery (analyzes tx history)
```bash
python3 discovery.py 0xYourAddress --include-l2
```

### Web UI
```bash
cd web_ui && python3 -m http.server 8080
# Open http://localhost:8080 - connect MetaMask
```

### Docker (production)
```bash
docker-compose up -d
# API at http://localhost:8000
# Web UI at http://localhost:8080
```

## Architecture

```
                    +----------------+
                    | lost_eth.py    | <- Master CLI
                    +-------+--------+
                            |
        +---------+---------+---------+---------+---------+
        |         |         |         |         |         |
    scanner_v2  airdrop  nft_scanner monitor   hunt    discovery
        |         |         |         |         |         |
        +---------+---------+---------+---------+---------+
                            |
                    +-------+--------+
                    | scanner core  |
                    | (MultiRPC)    |
                    +-------+--------+
                            |
                    +-------+--------+
                    | 9 EVM chains  |
                    +----------------+
```

## Modules

### Core Scanner (`scanner_v2.py`)
Async multi-chain scanner with concurrent.gather for sub-second scans.
- 9 chains, 100+ contracts, 91 tokens
- Multi-RPC fallback per chain
- 4 balance check types

### Discovery Engine (`discovery.py`)
Goes beyond static DB - analyzes tx history to find ANY contract interacted with.
- Fetches from Blockscout API
- Probes balance via 3 different methods per contract
- Cross-chain support

### Airdrop Checker (`airdrop_checker.py`)
Detects holdings of 20+ historical airdrops:
UNI, ENS, OP (3 rounds), ARB, 1INCH, DYDX, LOOKS, HOP, BLUR, AEVO, W, STRK, ZRO, ENA, ETHFI, REZ, EIGEN, ETHFI, etc.

### NFT Scanner (`nft_scanner.py`)
Checks ERC-721 holdings against 33 top collections (BAYC, CryptoPunks, Azuki, etc.)

### Monitor (`monitor.py`)
Continuous diff-based monitoring with Discord/generic webhook alerts.

### Bytecode Analyzer (`bytecode_analyzer.py`)
Forensic profiler:
- Function selector extraction (PUSH4)
- Critical opcode detection
- Proxy pattern (EIP-1167, 1967, 2535)
- Storage slot dump
- Auto-classification

### Storage DB (`storage_db.py`)
SQLite persistence layer for scan history, findings, alerts, contract cache.

### REST API (`api_server.py`)
FastAPI server exposing all functionality:
- `POST /scan` - scan addresses
- `POST /airdrops` - check airdrops
- `POST /nfts` - check NFTs
- `POST /withdraw_data` - generate raw tx
- `GET /docs` - interactive Swagger UI

### Telegram Bot (`telegram_bot.py`)
Self-hosted bot. Set `LOST_ETH_BOT_TOKEN` and run.

### Browser Extension (`browser_extension/`)
Chrome MV3 extension. Auto-detects addresses on Etherscan/Arbiscan and offers one-click scan.

## API Reference

See `/docs` endpoint when running `api_server.py`.

## Configuration

### Add a new chain
Edit `chains.json`:
```json
{
  "newchain": {
    "chain_id": 12345,
    "name": "New Chain",
    "explorer": "https://newchain.io",
    "rpcs": ["https://rpc.newchain.io"],
    "native_token": "ETH"
  }
}
```

### Add a new contract
Edit `contracts_multichain.json`:
```json
{
  "chain": "ethereum",
  "name": "My Contract",
  "address": "0x...",
  "balance_check": "etherdelta",
  "withdraw_method": "withdraw(address,uint256)",
  "category": "USER_DEPOSITS"
}
```

## Performance Benchmarks

On a modest 4-core VM with public RPCs:

| Operation | Time | RPC Calls |
|-----------|------|-----------|
| Single chain scan (1 addr) | 0.4s | ~20 |
| All chains scan (1 addr) | 4-5s | ~250 |
| Discovery (full tx history) | 6-10s | varies |
| 50-address bulk scan | ~30s | ~12,000 |
| Airdrop check (20 tokens) | 0.5s | 20 |
| NFT scan (33 collections) | 0.8s | 33 |

## Ethical Use

This toolkit reads only PUBLIC on-chain state. Recovery requires the private key
of the address being scanned. Do not use to attempt extraction of funds belonging
to others. Authors disclaim liability for misuse.

## Roadmap

- [ ] Subgraph (TheGraph) integration for historical analytics
- [ ] WebSocket streaming for live updates
- [ ] PostgreSQL backend option
- [ ] Multi-user authentication for hosted API
- [ ] Mobile-friendly PWA
- [ ] IPFS-pinned web UI
- [ ] Hardware wallet (Ledger/Trezor) signing
