# Lost ETH Scanner Suite v3.0

Production-grade toolkit for discovering and recovering forgotten Ethereum funds across mainnet and L2 networks.

## Tools

| Tool | Description | Lines |
|------|-------------|-------|
| `lost_eth.py` | **Master CLI** - unified entry point with subcommands | 180 |
| `scanner_v2.py` | Async multi-chain scanner with native + token + DEX checks | 380 |
| `airdrop_checker.py` | Detect airdrop holdings (20+ historical airdrops) | 280 |
| `nft_scanner.py` | Detect NFT holdings (33 top collections) | 180 |
| `monitor.py` | Continuous watch with diff-detection and webhooks | 170 |
| `dead_contract_hunter.py` | Forensic classification of dead contracts | 280 |
| `bytecode_analyzer.py` | Deep bytecode analysis: selectors, opcodes, classification | 280 |
| `hd_wallet_scanner.py` | Bulk-scan many addresses (HD wallet derivation) | 60 |
| `withdraw_helper.py` | Generate raw withdraw tx data for offline signing | 90 |
| `api_server.py` | FastAPI REST server exposing all functionality | 280 |
| `web_ui/index.html` | Browser UI with MetaMask integration | 547 |

**Total:** ~2,700 lines of code, ~1,000 lines of curated data

## Database

| File | Records |
|------|---------|
| `chains.json` | 9 chains (ETH, Arbitrum, Optimism, Base, Polygon, zkSync, Linea, Scroll, BSC) with multi-RPC fallback |
| `contracts_multichain.json` | **107 forgotten contracts** with categories and metadata |
| `tokens_multichain.json` | **91 tokens** across 8 chains |
| `dead_contracts_db.json` | Curated dead contract registry (15 famous cases) |

## Quick Start

```bash
# Install
pip install aiohttp certifi requests fastapi uvicorn

# Master CLI
python3 lost_eth.py stats                                    # show DB info
python3 lost_eth.py scan 0xAddr1 0xAddr2 --include-native    # full scan
python3 lost_eth.py airdrops 0xAddr                          # airdrop check
python3 lost_eth.py nfts 0xAddr                              # NFT holdings
python3 lost_eth.py monitor 0xAddr --interval 60             # continuous watch
python3 lost_eth.py hunt 0xCONTRACT                          # forensic classify
python3 lost_eth.py withdraw 0xCONTRACT 0xTOKEN AMOUNT_WEI   # raw tx
python3 lost_eth.py api                                      # REST server
python3 lost_eth.py hd --addresses-file addresses.txt        # bulk

# Direct tools (legacy)
python3 scanner_v2.py 0xAddr --concurrency 80
python3 bytecode_analyzer.py 0xCONTRACT --chain ethereum

# Web UI
cd web_ui && python3 -m http.server 8080
# Open http://localhost:8080
```

## Performance

- **scanner_v2**: 107 contracts x 9 chains x 91 tokens scanned in ~4s with ~250 RPC calls
- **airdrop_checker**: 20 airdrops checked in ~0.05s
- **nft_scanner**: 33 collections checked in ~0.08s
- **bytecode_analyzer**: full decode + classification in ~1-2s
- **API server**: handles 50 addresses per request

## REST API

Once `api_server.py` is running on port 8000:

```bash
# Get stats
curl http://localhost:8000/

# Scan addresses
curl -X POST http://localhost:8000/scan \
  -H "Content-Type: application/json" \
  -d '{"addresses": ["0xAddr"], "include_native": true}'

# Check airdrops
curl -X POST http://localhost:8000/airdrops \
  -d '{"addresses": ["0xAddr"]}'

# Generate withdraw tx
curl -X POST http://localhost:8000/withdraw_data \
  -d '{"contract": "0x...", "token": "0x0...0", "amount_wei": "1000000000000000000", "method_type": "etherdelta"}'
```

Interactive docs: `http://localhost:8000/docs`

## Architecture

```
lost_eth.py (Master CLI)
       |
  +----+----+--------+--------+--------+--------+
  |    |    |        |        |        |        |
scan airdrops nfts monitor hunt withdraw api
  |    |    |        |        |        |        |
  +----+----+--------+--------+--------+--------+
       |
   scanner_v2 (core engine)
       |
  +----+----+----+----+----+
  |    |    |    |    |    |
chains contracts tokens dead_db nft_db airdrop_db
   (multi-RPC fallback)
       |
  9 EVM chains: Ethereum, Arbitrum, Optimism, Base,
                Polygon, zkSync, Linea, Scroll, BSC
```

## What Gets Detected

### Stuck Balances (Recoverable by depositor)
- DEX deposits: IDEX 1.0, EtherDelta v1/v2/v3, Token.Store, Saturn, DDEX
- Lending: Compound v1, Aave v2 deprecated, MakerDAO SAI
- Yield farms: SushiSwap MasterChef, PancakeSwap, QuickSwap
- L2 protocols: GMX V1, Velodrome V1, Camelot, BaseSwap, Aerodrome
- Bridges: Hop Protocol, Across, Polygon PoS

### Token Holdings (Specific to address)
- Airdrops (20+): UNI, ENS, OP, ARB, 1INCH, DYDX, LOOKS, HOP, BLUR, AEVO, W, STRK, ZRO, ENA, ETHFI, REZ, EIGEN, etc.
- DAO tokens (1:100 redemption via WithdrawDAO)
- Gas tokens: GST2, CHI (free gas refunds)
- NFTs: BAYC, CryptoPunks, Azuki, CloneX, Doodles, Pudgy Penguins, +28 more

### Frozen (Documented, not recoverable)
- 444,615 ETH in 4 Parity multisigs (Nov 2017 incident)
- The DAO original (hard-forked away)

## Verified Working Test

Running on `0xd3301469347BaD6A767b2bf4af5Da486eeFb4cdf`:
```
NATIVE WALLET BALANCES
  ETHEREUM    0.000059 ETH

[ETHEREUM]
  FOUND in IDEX 1.0 -> 0.011616 ETH

Scan took 4.14s, 243 RPC calls (98% success)
```

## Ethical Use

- Reads only PUBLIC on-chain state
- Generated transactions must be signed by the address owner via wallet
- No exploitation of bugs or extraction of others' funds
- Educational and self-recovery purposes

## License

MIT - see repository root.
