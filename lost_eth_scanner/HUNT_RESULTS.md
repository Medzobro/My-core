# 🏴‍☠️ Lost ETH Hunt — Comprehensive Forensic Report

> **Goal**: Identify forgotten/dead Ethereum contracts holding recoverable ETH.
> **Scope**: 365 contracts across 20 chains. Native ETH + 9 stablecoin/wrapped balances.
> **Status**: ⚡ Active hunt — May 2026

---

## 🎯 KEY FINDING: 2,247 ETH (~$5.6M) UNCLAIMED IN CRYPTOPUNKS

**For the first time in this codebase, we identified individually addressable, recoverable balances.**

CryptoPunks Marketplace (V2: `0xb47e3cd837dDF8e4c57F05d70Ab865de6e193BBB`)
holds **3,332 ETH**. By scanning all 28,538 historical `PunkBought` events
and querying `pendingWithdrawals(address)` for each of the 6,383 unique
sellers, we found:

- **94 addresses** with non-zero `pendingWithdrawals`
- **Total: 2,247.6 ETH** (~$5.6M USD)
- **Top single address: 153.45 ETH**

These funds belong to specific seller addresses. Anyone with the **private key** to
one of those addresses can call `withdraw()` and claim instantly.

📄 Full list: [`cryptopunks_pending.json`](./cryptopunks_pending.json)

### Top 10 unclaimed (CryptoPunks V2)

| Amount | Address |
|--------|---------|
| 153.45 ETH | `0x8be6ad79f67d1b76eba486b0ef4fd2c9bd1cd067` |
| 115.00 ETH | `0x131b2b74823bec1589fbfd7bf5842a765721c704` |
| 111.90 ETH | `0x0a68c97fc10e77ebe065a4959ae3e7e4896802b6` |
| 107.50 ETH | `0x29664e652ca8f8f2d95de3b33cc0ae7247fc0aa9` |
| 103.35 ETH | `0xcafbf7952763c7237d2848a553e3146cbdd08602` |
| 95.00 ETH | `0x062c5432107e3b9ad924512209a7468b5c200fcd` |
| 81.00 ETH | `0x60c7db709ebf1c3cf01057245eaaf79c6796e4e4` |
| 75.00 ETH | `0x44874658340fa4ebe399546841319655fb606a45` |
| 67.55 ETH | `0x16a76a88f866b80f9b5f4c916d6d79c953198fcf` |
| 62.00 ETH | `0x59f4509017edcccc365881ba6d661a3bc63ebb79` |

### How to recover (if YOU control any of these addresses)
```python
# Using web3.py
from web3 import Web3
w3 = Web3(Web3.HTTPProvider('https://ethereum-rpc.publicnode.com'))
contract = w3.eth.contract(
    address='0xb47e3cd837dDF8e4c57F05d70Ab865de6e193BBB',
    abi=[{'name':'withdraw','type':'function','inputs':[],'outputs':[],
          'stateMutability':'nonpayable'}])
acct = w3.eth.account.from_key(MY_PRIVATE_KEY)
tx = contract.functions.withdraw().build_transaction({
    'from': acct.address, 'gas': 100000, 'nonce': w3.eth.get_transaction_count(acct.address),
})
signed = acct.sign_transaction(tx)
w3.eth.send_raw_transaction(signed.rawTransaction)
```

---

## 📊 GLOBAL SCAN — TOTAL ETH ACROSS 365 CONTRACTS / 20 CHAINS

| Chain | Native | Stable+Wrapped USD |
|-------|--------:|-------------------:|
| Ethereum | 825,095 ETH (~$2.1B) | $509M |
| Polygon | 34,764 MATIC | $2M |
| Base | 927.5 ETH | $0 |
| Moonbeam | 342.6 GLMR | $0 |
| BSC | trace | $1.5M |
| Arbitrum | trace | $428K |
| Gnosis | 32 xDAI | $108K |
| Optimism | trace | $26K |
| Celo | 12 CELO | $0 |
| zkSync | 7.17 ETH | $0 |

---

## 🔬 CLASSIFIED RECOVERABILITY

### A. ❌ PERMANENTLY LOST (~444,617 ETH)
- Polkadot Foundation Parity multisig: **306,277 ETH**
- Iconomi Parity multisig: **114,939 ETH**
- Musiconomi Parity multisig: **16,476 ETH**
- Unknown Parity Multisig #4: **6,925 ETH**

These are all Parity Multi-Sig contracts whose `Library` was suicided in November 2017
by `devops199`. The wallets call `delegatecall` into a destroyed library, so EVERY
function reverts. No recovery is possible without an Ethereum hard fork.

### B. ❌ CRYPTOGRAPHICALLY LOCKED (~216,225 ETH)
Tornado Cash pools (100/10/1/0.1 ETH denominations + USDC/USDT/DAI variants).
Each deposit creates a Poseidon commitment. To withdraw, the user must produce a
zero-knowledge proof using the secret note generated at deposit time. Without the
note: zero recovery path. The pools are also OFAC-sanctioned.

### C. ❌ DAO-TOKEN GATED (81,914 ETH)
**WithdrawDAO** (`0xbf4ed7b27f1d666546e30d74d50d173d20bca754`):
- `withdraw()` reads `balanceOf(msg.sender)` from the original DAO token
  (`0xbb9bc244d798123fde783fcc1c72d3bb8c189413`)
- Pays 1 ETH per 100 DAO tokens to the caller
- Requires owning DAO tokens minted in May 2016

If you DID participate in The DAO (May 2016), check your DAO balance.

### D. ⚠️ USER-STATE GATED — RECOVERABLE WITH SPECIFIC PRIVATE KEYS
The big find. These contracts have public `withdraw()`, but the function only pays
out the caller's **own** stored balance. If you control an address with a non-zero
internal balance, you can withdraw.

| Contract | Address | Total ETH | Recovery model |
|----------|---------|-----------|----------------|
| **CryptoPunks V2** | `0xb47e3cd8...e193BBB` | 3,332 | `pendingWithdrawals[seller]` — see ★ list above |
| **CryptoPunks V1 (old)** | `0x6BA6f220...66DB8D` | 4.64 | `pendingWithdrawals[seller]` |
| **IDEX 1.0** | `0x2a0c0DBE...050c208` | 16,168 | `tokens[0x0][user]` (depositor balance) |
| **ForkDelta / EtherDelta v3** | `0x8d12A197...cC6819` | 15,222 | `tokens[0x0][user]` |
| **Token.Store** | `0x1ce7AE55...e6Ee33D8` | 633 | `tokens[0x0][user]` |
| **Friend.tech** (Base) | `0xCF205808...d4A4d4` | 928 | `sellShares()` — need shares |

🛠 To check if YOU have funds in any of these, use:
```bash
python3 check_my_addresses.py --file my_addresses.txt
```
or edit `MY_ADDRESSES` in `check_my_addresses.py`.

### E. 🟡 OWNER-CONTROLLED (recoverable only by named admin)
Contracts with `sweep()` / `rescue()` / `recover()` callable only by `owner()`.

| Contract | Balance | Owner |
|----------|---------|-------|
| dYdX Solo v1 | $6.7M USDC/DAI/WETH | `0xba2906b1...8b1b53` |
| Synapse Old Bridge | 5.6 ETH + $1.2M USDC | governance multisig |
| QiDao Old | 34,763 MATIC | `0x3feacf90...` |
| Wormhole Token Bridge | $320M | governance |

---

## 📂 FILE INVENTORY

| File | Purpose |
|------|---------|
| `chains.json` | RPC config for 20 chains |
| `contracts_multichain.json` | 365 candidate contracts |
| `contracts_extra.json` | Failed bridges/DeFi adds (172) |
| `contracts_airdrops.json` | 86 merkle airdrop claim contracts |
| `dead_contract_hunter.py` | Initial 16-contract triage |
| `multichain_audit.py` | Wide async balance + selector scan |
| `deep_audit.py` | + ERC-20 token balance + sweep heuristics |
| `bytecode_disasm.py` | EVM static analyzer for `withdraw()` |
| `exploit_simulator.py` | eth_call fuzzing of public funcs |
| `source_fetcher_v2.py` | Pulls verified Solidity from Sourcify |
| `cryptopunks_pending_scan.py` | ★ Found the 2,247 ETH unclaimed |
| `unclaimed_balances_scan.py` | Same approach for EtherDelta/IDEX/Token.Store |
| `check_my_addresses.py` | **Personal recovery tool** |
| `cryptopunks_pending.json` | ★ Output: 94 unclaimed seller balances |
| `deep_audit_results.json` | Full audit dump |
| `multichain_audit_results.json` | Wider audit dump |
| `sources/*.sol` | Verified contract sources for review |

---

## 🚀 NEXT STEPS

- [x] Expand contract DB to 350+
- [x] Multi-chain scan (20 chains)
- [x] Stuck ERC-20 detection
- [x] EVM bytecode static analyzer
- [x] Sourcify integration
- [x] CryptoPunks pendingWithdrawals scan
- [ ] (Running) EtherDelta + IDEX + Token.Store unclaimed-balance scan
- [ ] HD-wallet sweep against historic deposit lists
- [ ] Failed-bridge user-position scan (Multichain, Nomad)
- [ ] Old airdrop merkle proof verification
- [ ] Etheria 1.0/1.1/1.2 unclaimed plot owner scan

---

## ⚖️ ETHICS

- **Recovering YOUR OWN funds**: 100% legitimate. Your private key, your right.
- **Calling `withdraw()` on a contract for an address you don't own**: not possible — the contract pays `msg.sender`.
- **Trying to exploit a real vulnerability for profit**: criminal in most jurisdictions, regardless of "abandoned" framing.

This codebase is for **personal recovery** of forgotten funds you are entitled to claim.
