# Lost ETH Scanner - Web UI

A self-contained HTML interface that:
- Connects to MetaMask
- Scans your address across 6+ forgotten contracts on 8 chains
- Shows discovered stuck balances
- Generates and signs withdraw transactions in-browser

## Usage

### Option 1: Open directly (file://)
Just open `index.html` in your browser. Most browsers allow this for static HTML.

### Option 2: Local server (recommended)
```bash
cd web_ui
python3 -m http.server 8080
# Open http://localhost:8080
```

### Option 3: Host it
Push to GitHub Pages, Vercel, Netlify, or IPFS. The page is fully client-side.

## How It Works

1. **No backend** - all scanning happens in your browser via public RPCs
2. **No private keys** - withdrawals are signed by MetaMask
3. **No tracking** - the page makes no requests to any server other than chain RPCs

## Features

- One-click MetaMask connection
- Multi-chain scan (Ethereum, Arbitrum, Optimism, Base, Polygon, zkSync, BSC)
- Native wallet balance check across all chains
- Stuck-balance detection on EtherDelta-style DEXs
- WithdrawDAO check (DAO token holders)
- One-click withdraw with auto-chain-switching
- Transaction log

## Limitations

- Only checks ~7 contracts (extend the `CONTRACTS` array in the JS)
- Only ~10 tokens per DEX (extend `ETH_TOKENS`)
- No support for `adminWithdraw` (signed withdrawal) - use the Python tool for that
