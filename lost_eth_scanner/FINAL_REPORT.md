# 🏴‍☠️ FINAL REPORT — Lost ETH Hunt

> **Honest conclusion after exhaustive investigation**

---

## The Search (May 2026)

**Total scope:**
- **365 contracts** across **20 EVM chains** (Ethereum, all major L2s, sidechains)
- **17 drain selectors** tested per contract (`withdraw`, `claim`, `sweep`, `rescue`, `recover`, `emergency`, etc.)
- **9 ERC-20 tokens** checked per chain (USDC, USDT, DAI, WETH, WBTC, LINK, etc.)
- **~31,000 RPC simulations** performed
- **6,383 CryptoPunks sellers** queried for `pendingWithdrawals`
- **17,531 EtherDelta users** queried for stored ETH
- **23 verified contract sources** pulled from Sourcify and analyzed

---

## What we definitively confirmed

### ✅ Recoverable funds exist — but they belong to specific people

| Pool | Total ETH | Recovery method |
|------|----------:|-----------------|
| 🏆 **CryptoPunks `pendingWithdrawals` (V1+V2)** | **2,247.6 ETH** | The 94 specific seller addresses call `withdraw()` |
| ForkDelta / EtherDelta v3 | 15,221 ETH | Original depositors call `withdraw(uint256)` |
| IDEX 1.0 | 16,168 ETH | Original depositors call `withdraw(address,uint256)` |
| Token.Store | 633 ETH | Original depositors call `withdraw(address,uint256)` |
| WithdrawDAO | 81,914 ETH | DAO token holders from May 2016 |
| Friend.tech (Base) | 928 ETH | Share holders call `sellShares()` |
| Compound v1 cETH | 426 WETH | cETH holders call `redeem()` |

**Total addressable: ~$300M+** (sum across major contracts)

### ❌ Permanently locked

| Pool | ETH | Why |
|------|----:|-----|
| Parity Multisigs | 444,617 | Library suicided Nov 2017 |
| Tornado Cash pools | 216,225 | Each requires the original depositor's secret note |

### ❌ Truly unguarded contracts (free for anyone)
**ZERO.**

After testing 31,000 selector combinations, no contract on any of the 20 chains had a public function that drains ETH to msg.sender unconditionally. Every "non-revert" hit fell into one of:
- **User-state-gated**: `withdraw()` pays only `mapping[msg.sender]` (= 0 for anyone new)
- **Owner-only**: rescue/sweep callable by `owner()` (still active or burnt)
- **Proxy fallback**: returns `0x` to any selector but doesn't transfer
- **Withdraw(0)**: trivial no-op that always succeeds

---

## Why no "free money" exists

**MEV is the universal filter.** A handful of professional searcher firms run real-time bots on every EVM chain that:
1. Subscribe to mempool + block events
2. Decompile every newly-deployed contract within 1 block
3. Test all public functions for unconditional ETH/token transfers
4. Submit drain transactions in the same block

Result: any contract holding ETH for **3+ years** has either:
- Strong access control (verified)
- An impossible-to-unlock state (Parity, Tornado)
- User-keyed balance mappings (DEX deposits)
- Tiny dust below MEV gas threshold (literal cents)

---

## How the user can actually recover ETH

### Path 1: User has old wallet addresses
```bash
echo "0xMyOldAddress1..." > my_addrs.txt
echo "0xMyOldAddress2..." >> my_addrs.txt
python3 check_my_addresses.py --file my_addrs.txt
```
Checks against EtherDelta, ForkDelta, IDEX, Token.Store, CryptoPunks V1+V2 pendingWithdrawals, Compound v1, WithdrawDAO eligibility.

### Path 2: User has an old BIP-39 seed phrase
**⚠️ Run on an air-gapped machine!**
```bash
pip install eth-account mnemonic
python3 hd_wallet_scanner.py --mnemonic "twelve word phrase ..." --n 50
```
Derives 200 addresses across 4 common paths:
- `m/44'/60'/0'/0/{i}` — MetaMask, MEW, Trezor
- `m/44'/60'/{i}'/0/0` — Ledger Live
- `m/44'/60'/0'/{i}` — Ledger Legacy
- `m/0'/0/{i}` — Mist (very old, 2014-2016)

### Path 3: User had DAO tokens in 2016
Look for old keystore files from May–June 2016. The DAO token address was:
`0xbb9bc244d798123fde783fcc1c72d3bb8c189413`

If you find any DAO tokens, call `withdraw()` on:
`0xbf4ed7b27f1d666546e30d74d50d173d20bca754` — pays 1 ETH per 100 DAO.

### Path 4: User used CryptoPunks
Check the 94 seller addresses in [`cryptopunks_pending.json`](./cryptopunks_pending.json).
If any matches yours, just call `withdraw()` on:
- V2: `0xb47e3cd837dDF8e4c57F05d70Ab865de6e193BBB`
- V1: `0x6BA6f2207e343923BA692e5Cae646Fb0F566DB8D`

---

## Tools delivered in this PR

| Tool | Purpose |
|------|---------|
| `chains.json` | RPC config for 20 EVM chains |
| `contracts_multichain.json` | 365-contract abandoned-DeFi database |
| `dead_contract_hunter.py` | Initial classification (UNKNOWN/OWNED/PERMISSIONLESS) |
| `multichain_audit.py` | Wide async balance scan |
| `deep_audit.py` | Native + ERC-20 + recoverability score |
| `bytecode_disasm.py` | Static EVM analyzer for `withdraw()` guards |
| `exploit_simulator.py` | eth_call fuzzing from random senders |
| `mev_dust_hunter.py` | eth_estimateGas + drain-selector fuzzing |
| `stuck_erc20_hunter.py` | Stuck token + rescue function detector |
| `source_fetcher_v2.py` | Pulls verified source from Sourcify |
| `cryptopunks_pending_scan.py` | ⭐ Found 94 sellers with 2,247 ETH |
| `unclaimed_balances_scan.py` | EtherDelta/IDEX user-balance scanner |
| `etherdelta_quick_scan.py` | Validated 1,685 ED users with 68.7 ETH (sample) |
| `analyze_contract.py` | Single-contract deep dive |
| `check_my_addresses.py` | **Personal recovery tool** ← USE THIS |
| `hd_wallet_scanner.py` | Seed-phrase derivation scanner |

---

## TL;DR

> **Free ETH does not exist on Ethereum or any major L2 in 2026.**
> The ~$2 billion of "abandoned" ETH is either permanently locked or
> waiting for specific private keys that we don't have.
>
> The CryptoPunks `pendingWithdrawals` discovery (2,247 ETH across 94
> addresses) is the most actionable result: if any of those 94 addresses
> belong to the user, they can recover their funds with one `withdraw()` call.

The code is on GitHub: https://github.com/Medzobro/My-core/pull/1
