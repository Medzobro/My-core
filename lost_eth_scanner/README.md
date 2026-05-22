# Lost ETH Scanner Suite

Multi-chain async toolkit for discovering and recovering forgotten Ethereum funds.

## Components

| Tool | Description |
|------|-------------|
| **`scanner_v2.py`** | Async multi-chain scanner. 9 chains, 32+ contracts, 91 tokens. Sub-second scans. |
| **`monitor.py`** | Continuous watcher with diff-detection and Discord webhook alerts. |
| **`web_ui/index.html`** | Browser-based UI with MetaMask integration for one-click withdrawals. |
| **`dead_contract_hunter.py`** | Forensic classifier - tags contracts as FROZEN, USER_DEPOSITS, etc. |
| **`withdraw_helper.py`** | Generates raw transaction data for offline signing. |

## Database Files

| File | Contents |
|------|----------|
| `chains.json` | 9 chains with multi-RPC fallback (Ethereum, Arbitrum, Optimism, Base, Polygon, zkSync, Linea, Scroll, BSC) |
| `contracts_multichain.json` | 32 forgotten contracts across all chains |
| `tokens_multichain.json` | 91 popular tokens to scan inside DEXs |
| `dead_contracts_db.json` | Curated dead contract registry with classifications |

## Quickstart

### 1. Install
```bash
pip install aiohttp certifi requests
```

### 2. Scan an address
```bash
python3 scanner_v2.py 0xYourAddress
# OR with options
python3 scanner_v2.py --chains ethereum,arbitrum --concurrency 100 --include-native 0xAddr
```

### 3. Monitor continuously
```bash
python3 monitor.py 0xAddr1 0xAddr2 --interval 300 --webhook https://discord.com/api/webhooks/...
```

### 4. Web UI
```bash
cd web_ui && python3 -m http.server 8080
# Open http://localhost:8080
```
Or just open `web_ui/index.html` directly in a browser.

### 5. Generate withdraw transaction
```bash
python3 withdraw_helper.py 0xCONTRACT 0xTOKEN AMOUNT_WEI
```

## Performance

- **scanner_v2**: 32 contracts x 9 chains x 91 tokens = ~200 RPC calls per address in **~1.5 seconds**
- **Concurrency** configurable (default 80 simultaneous calls)
- **SSL** verified via `certifi` for sandboxed environments
- **Multi-RPC** automatic failover (4-5 endpoints per chain)

## Verified Findings

Tested working - detected `0.011616 ETH` stuck in IDEX 1.0 for `0xd3301469347BaD6A767b2bf4af5Da486eeFb4cdf` (sample address from on-chain history).

## Ethical Use

- Read-only on-chain queries
- Withdrawals require the private key of the address being recovered
- No exploitation of bugs, no extraction of others' funds
- Educational and self-recovery use only
