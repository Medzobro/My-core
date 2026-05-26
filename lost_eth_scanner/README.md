# 🏴‍☠️ Lost ETH Scanner

> **Forensic toolkit for finding recoverable ETH and ERC-20 funds in abandoned smart contracts across 20 EVM chains.**

[![Status](https://img.shields.io/badge/status-active-green.svg)]()
[![Chains](https://img.shields.io/badge/chains-20-blue.svg)]()
[![Contracts DB](https://img.shields.io/badge/contracts-365-orange.svg)]()
[![ETH Indexed](https://img.shields.io/badge/ETH%20found-2%2C247.6-brightgreen.svg)]()

---

## 🎯 Key Finding (May 2026)

**2,247.6 ETH (~$5.6M)** unclaimed in CryptoPunks `pendingWithdrawals` across **94 specific seller addresses** — recoverable by anyone holding the private key for those addresses.

📄 Full list: [`results/cryptopunks_pending.json`](./results/cryptopunks_pending.json)

📊 Detailed reports:
- [`FINAL_REPORT.md`](./FINAL_REPORT.md) — Honest summary of the entire hunt
- [`HUNT_RESULTS.md`](./HUNT_RESULTS.md) — Detailed per-contract analysis
- [`RECOVERY_GUIDE.md`](./RECOVERY_GUIDE.md) — How YOU can recover funds (Arabic + English)

---

## 📂 Repository Structure

```
lost_eth_scanner/
├── README.md                  ← you are here
├── FINAL_REPORT.md            ← honest conclusions
├── HUNT_RESULTS.md            ← detailed findings
├── RECOVERY_GUIDE.md          ← practical recovery instructions
├── requirements.txt
│
├── data/                      ← input databases
│   ├── chains.json            ← 20-chain RPC config
│   ├── contracts_multichain.json   ← 365 abandoned contracts
│   ├── contracts_airdrops.json     ← 91 merkle airdrops
│   ├── contracts_extra.json
│   ├── contracts.json
│   └── tokens_multichain.json
│
├── results/                   ← scan outputs (JSON)
│   ├── cryptopunks_pending.json    ★ 2,247 ETH unclaimed
│   ├── deep_audit_results.json     ← all 365 contracts audited
│   ├── multichain_audit_results.json
│   ├── exploit_sim_results.json
│   ├── mev_dust_results.json
│   ├── stuck_erc20_results.json
│   ├── etherdelta_unclaimed_4700000_4720000.json
│   └── investigation_results.json
│
├── sources/                   ← verified Solidity from Sourcify (23 contracts)
│
├── docs/                      ← documentation pages
│
├── browser_extension/         ← Chrome extension for live scanning
├── web_ui/                    ← web dashboard (legacy)
├── tests/
└── legacy/                    ← deprecated scripts kept for reference
```

---

## 🛠 Tools by Purpose

### 🔍 Recovery Tools (use these first if you have any old wallets)

| Tool | What it does |
|------|--------------|
| [`check_my_addresses.py`](./check_my_addresses.py) | **★ Personal recovery tool** — scan YOUR addresses against 9 abandoned contracts |
| [`hd_wallet_scanner.py`](./hd_wallet_scanner.py) | Derive 200 addresses from a BIP-39 seed phrase, scan all of them (run **offline**) |
| [`scanner.py`](./scanner.py) / [`scanner_v2.py`](./scanner_v2.py) | Bulk address scanning |
| [`withdraw_helper.py`](./withdraw_helper.py) | Helper to build withdrawal transactions |

### 🔬 Forensic Scanners

| Tool | What it does |
|------|--------------|
| [`multichain_audit.py`](./multichain_audit.py) | Wide async balance + selector scan across 20 chains |
| [`deep_audit.py`](./deep_audit.py) | Native + 9 ERC-20 + recoverability score per contract |
| [`mev_dust_hunter.py`](./mev_dust_hunter.py) | eth_call + eth_estimateGas fuzzing for unguarded drains |
| [`stuck_erc20_hunter.py`](./stuck_erc20_hunter.py) | Stuck USDC/USDT/DAI on contracts with rescue() |
| [`exploit_simulator.py`](./exploit_simulator.py) | Random-sender simulation of all drain selectors |
| [`cryptopunks_pending_scan.py`](./cryptopunks_pending_scan.py) | ★ Found 2,247 ETH unclaimed (94 sellers) |
| [`unclaimed_balances_scan.py`](./unclaimed_balances_scan.py) | EtherDelta/IDEX/TokenStore user balance scan |
| [`etherdelta_quick_scan.py`](./etherdelta_quick_scan.py) | Faster ED scan with smaller block ranges |

### 🧬 Analysis Tools

| Tool | What it does |
|------|--------------|
| [`bytecode_disasm.py`](./bytecode_disasm.py) | EVM static analyzer — detects `withdraw()` guards |
| [`bytecode_analyzer.py`](./bytecode_analyzer.py) | High-level bytecode pattern matcher |
| [`analyze_contract.py`](./analyze_contract.py) | Single-contract deep-dive investigator |
| [`source_fetcher_v2.py`](./source_fetcher_v2.py) | Pulls verified Solidity from Sourcify |
| [`dead_contract_hunter.py`](./dead_contract_hunter.py) | Initial classification: PERMISSIONLESS/OWNED/EOA |
| [`nft_scanner.py`](./nft_scanner.py) | NFT-specific abandoned-contract scanner |
| [`airdrop_checker.py`](./airdrop_checker.py) | Merkle airdrop eligibility checker |

### 🌐 Infrastructure

| Tool | What it does |
|------|--------------|
| [`api_server.py`](./api_server.py) | REST API exposing scanner endpoints |
| [`telegram_bot.py`](./telegram_bot.py) | Telegram notifications for scan results |
| [`monitor.py`](./monitor.py) | Long-running monitor for new abandoned contracts |
| [`storage_db.py`](./storage_db.py) | SQLite persistence layer |
| [`discovery.py`](./discovery.py) | Auto-discovery of new candidate contracts |
| [`browser_extension/`](./browser_extension/) | Chrome extension for live MetaMask integration |

---

## 🚀 Quick Start

### 1. Install dependencies
```bash
pip install -r requirements.txt
# Core deps: aiohttp, certifi, requests
# For HD wallet derivation: eth-account, mnemonic
```

### 2. Run a comprehensive audit (1 minute)
```bash
python3 deep_audit.py
# Output: results/deep_audit_results.json
```

### 3. Check YOUR old addresses
```bash
# Edit MY_ADDRESSES list inside check_my_addresses.py, OR:
echo "0xYourOldAddress1..." > my_addrs.txt
echo "0xYourOldAddress2..." >> my_addrs.txt
python3 check_my_addresses.py --file my_addrs.txt
```

### 4. (Offline only) Check a BIP-39 seed phrase
```bash
# ⚠️ Run on an air-gapped machine
pip install eth-account mnemonic
python3 hd_wallet_scanner.py --mnemonic "twelve word seed phrase ..." --n 50
```

---

## 📊 What's Been Mapped

| Chain | Contracts | Native ETH/native | ERC-20 USD value |
|-------|----------:|-----------------:|------------------:|
| Ethereum | 224 | 825,095 ETH | $509M |
| Polygon | 22 | 34,764 MATIC | $2M |
| BSC | 22 | trace | $1.5M |
| Arbitrum | 18 | trace | $428K |
| Optimism | 12 | trace | $26K |
| Avalanche | 11 | trace | $20 |
| Fantom | 12 | trace | — |
| Base | 7 | 928 ETH | — |
| zkSync | 5 | 7.17 ETH | — |
| Linea | 4 | trace | — |
| Aurora | 4 | — | — |
| Cronos | 4 | — | — |
| Gnosis | 4 | 32 xDAI | $108K |
| Celo | 3 | 12 CELO | — |
| Metis | 3 | — | — |
| Moonbeam | 3 | 343 GLMR | — |
| Mantle | 2 | — | — |
| Mode | 2 | — | — |
| Blast | 2 | — | — |
| Scroll | 1 | — | — |

**Grand total mapped: ~$2.6 billion in abandoned contract holdings.**

---

## ⚖️ Ethics

- **Recovering YOUR OWN funds**: 100% legitimate. Your private key, your right.
- **Calling `withdraw()` on a contract for an address you don't own**: not possible — the contract pays `msg.sender`.
- **Trying to exploit a real vulnerability for profit**: criminal in most jurisdictions, regardless of "abandoned" framing.

This codebase is for **personal recovery** of forgotten funds you are entitled to claim, and for legitimate forensic / academic research.

---

## 📝 License

MIT — see [LICENSE](../LICENSE) if present.

---

## 🤝 Contributing

PRs welcome for:
- Additional candidate contracts (with research notes)
- New chain support
- New abandoned-DeFi rugs/bridges to investigate
- Documentation improvements
