# Lost ETH Scanner Suite v3.0

> Production-grade async multi-chain toolkit for discovering and recovering forgotten Ethereum funds. **107 contracts, 91 tokens, 20 airdrops, 33 NFT collections, 9 EVM chains.**

[![Tests](https://img.shields.io/badge/tests-14%2F14%20passing-brightgreen)]() [![Python](https://img.shields.io/badge/python-3.10+-blue)]() [![Docker](https://img.shields.io/badge/docker-ready-blue)]() [![License](https://img.shields.io/badge/license-MIT-green)]()

## Features

- **Multi-chain Scanner** - Async parallel scanning across 9 EVM chains (~4s for 107 contracts)
- **Discovery Engine** - Goes beyond static DB; analyzes tx history to find unknown contracts
- **Airdrop Checker** - 20+ historical airdrops (UNI, ENS, OP, ARB, BLUR, AEVO, EIGEN...)
- **NFT Scanner** - 33 top collections (BAYC, CryptoPunks, Azuki, CloneX...)
- **Bytecode Analyzer** - Forensic profiler with auto-classification
- **Continuous Monitor** - Diff-detection with Discord webhooks
- **REST API** - FastAPI server with Swagger docs at `/docs`
- **Telegram Bot** - Self-hosted scanner via Telegram
- **Browser Extension** - Chrome MV3 extension for Etherscan integration
- **Web UI** - MetaMask-integrated browser app
- **SQLite Storage** - Persistent scan history and contract cache
- **Master CLI** - One unified entry point with 11 subcommands
- **Docker Ready** - Single-command deployment with docker-compose
- **Tested** - 14 pytest tests covering core functionality

## Installation

```bash
git clone https://github.com/Medzobro/My-core
cd My-core/lost_eth_scanner
pip install -r requirements.txt
```

Or with Docker:

```bash
docker-compose up -d
```

## Quick Start

```bash
# Show all available commands
python3 lost_eth.py --help

# Stats about the database
python3 lost_eth.py stats

# Scan an address across all chains
python3 lost_eth.py scan 0xYourAddress --include-native

# Discover unknown contracts via tx history
python3 lost_eth.py discover 0xYourAddress --include-l2

# Check airdrops
python3 lost_eth.py airdrops 0xYourAddress

# Check NFTs
python3 lost_eth.py nfts 0xYourAddress

# Forensic analysis of any contract
python3 bytecode_analyzer.py 0x2a0c0DBEcC7E4D658f48E01e3fA353F44050c208

# Run continuous monitor with Discord alerts
python3 lost_eth.py monitor 0xAddr --interval 300 --webhook https://discord.com/...

# Start REST API server
python3 lost_eth.py api
# Visit http://localhost:8000/docs

# Start Telegram bot
LOST_ETH_BOT_TOKEN=your_token python3 telegram_bot.py
```

## Tools Inventory

| Tool | Lines | Description |
|------|------:|-------------|
| `lost_eth.py` | 200 | Master CLI with 11 subcommands |
| `scanner_v2.py` | 380 | Async multi-chain scanner |
| `discovery.py` | 220 | Tx-history-based contract discovery |
| `airdrop_checker.py` | 280 | 20+ airdrop detection |
| `nft_scanner.py` | 180 | 33 NFT collection scanner |
| `bytecode_analyzer.py` | 280 | Forensic bytecode profiler |
| `monitor.py` | 170 | Continuous diff-monitor |
| `dead_contract_hunter.py` | 280 | Forensic classifier |
| `storage_db.py` | 200 | SQLite persistence layer |
| `api_server.py` | 280 | FastAPI REST server |
| `telegram_bot.py` | 220 | Telegram interface |
| `web_ui/index.html` | 547 | Browser UI with MetaMask |
| `browser_extension/` | 100 | Chrome MV3 extension |
| `tests/test_core.py` | 130 | Pytest suite (14 tests) |
| `withdraw_helper.py` | 90 | Raw tx generator |
| `hd_wallet_scanner.py` | 60 | Bulk address scanner |
| **Total** | **~3,500** | **lines of code** |

## Database Inventory

| File | Records |
|------|---------|
| `chains.json` | 9 chains x 4-5 RPCs each |
| `contracts_multichain.json` | **107 contracts** with metadata |
| `tokens_multichain.json` | **91 tokens** across 8 chains |
| `dead_contracts_db.json` | 15 forensically-classified dead contracts |

## Documentation

See `docs/` directory:

- `docs/index.md` - Architecture and overview
- `docs/cli.md` - CLI reference
- `docs/contracts.md` - Contracts database guide
- `docs/airdrops.md` - Airdrop checker reference

## REST API

```bash
python3 api_server.py
# Open http://localhost:8000/docs for interactive Swagger UI
```

Endpoints:
- `GET /` - service info and stats
- `GET /chains` - list supported chains
- `GET /contracts?chain=...&category=...` - filter contracts
- `POST /scan` - scan addresses
- `POST /airdrops` - check airdrop holdings
- `POST /nfts` - check NFT holdings
- `POST /withdraw_data` - generate raw tx data

## Tests

```bash
pytest tests/ -v
# 14 passed in 0.17s
```

## Performance

Tested on a 4-core VM with public RPCs:

| Operation | Time | RPC Calls |
|-----------|-----:|----------:|
| Single chain scan | 0.4s | ~20 |
| All chains scan (107 contracts + 91 tokens) | ~4s | ~250 |
| Discovery (full tx history) | ~6-10s | varies |
| 50-address bulk scan | ~30s | ~12,000 |
| Airdrop check (20 tokens) | 0.05s | 20 |
| NFT scan (33 collections) | 0.08s | 33 |

## Verified Working

Confirmed detection of `0.011616 ETH` stuck in IDEX 1.0 for sample address `0xd3301469347BaD6A767b2bf4af5Da486eeFb4cdf`. Discovery Engine additionally identified an undocumented staking contract holding `0.0239 ETH`.

## Ethical Use

This toolkit reads only PUBLIC on-chain state. Recovery requires the private key
of the address being scanned. Do not use to attempt extraction of funds belonging
to others.

## Roadmap

- [x] Multi-chain scanner with 9 EVM chains
- [x] 100+ contract database
- [x] Discovery engine
- [x] REST API + Swagger
- [x] Telegram bot
- [x] Browser extension
- [x] SQLite persistence
- [x] Docker setup
- [x] CI/CD via GitHub Actions
- [x] pytest test suite
- [ ] Subgraph (TheGraph) integration
- [ ] Hardware wallet (Ledger/Trezor) signing flow
- [ ] PWA mobile-friendly UI
- [ ] IPFS deployment script
- [ ] Multi-language UI (Arabic + English)
- [ ] WebSocket streaming for live updates

## License

MIT
