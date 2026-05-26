# 🏴‍☠️ CryptoPunks Deep Recoverability Analysis

> Comprehensive forensic analysis of the 2,247 ETH unclaimed in CryptoPunks V2.
> Generated: May 2026

---

## Executive Summary

The CryptoPunks V2 marketplace contract (`0xb47e3cd837dDF8e4c57F05d70Ab865de6e193BBB`)
holds **3,332 ETH**. After exhaustive scanning:

- **2,247.6 ETH** sits in `pendingWithdrawals[]` across **94 specific addresses**
- **0 ETH** in active bids (all bids have been resolved or withdrawn)
- **~1,085 ETH** difference unaccounted for in our scan (possibly from before our event range)

The largest finding: **43 of the top 50 addresses are DORMANT EOAs** —
addresses with `nonce = 0` (never sent a transaction) and `balance = 0`.
These bear hallmarks of lost-key wallets.

---

## Source Code Audit Findings

The CryptoPunks V2 contract (verified via Sourcify) has **NO recovery backdoor**:

```solidity
function withdraw() {
    if (!allPunksAssigned) throw;
    uint amount = pendingWithdrawals[msg.sender];
    pendingWithdrawals[msg.sender] = 0;
    msg.sender.transfer(amount);
}
```

- ✅ No admin override
- ✅ No `transferPendingWithdrawal` function
- ✅ No `selfdestruct` opcode anywhere in the contract
- ✅ No fallback function (contract refuses random ETH)
- ✅ No upgradeability (Solidity 0.4.8, no proxy)
- ✅ The `owner` only controls initial assignment - cannot drain post-deployment

**Verdict:** Each pending withdrawal is cryptographically tied to its specific
recipient address. Recovery requires the **private key** for that address.

---

## The 43 Dormant Lost-Key Candidates

These addresses have all three forensic markers of **lost keys**:
1. Have unclaimed pendingWithdrawals (in CryptoPunks V2)
2. Have `nonce = 0` (never originated a transaction)
3. Have `balance = 0 ETH` on mainnet

| Rank | Pending ETH | Address | Status |
|-----:|------------:|---------|--------|
| 1 | 153.45 | `0x8be6ad79f67d1b76eba486b0ef4fd2c9bd1cd067` | DORMANT |
| 2 | 115.00 | `0x131b2b74823bec1589fbfd7bf5842a765721c704` | DORMANT |
| 3 | 111.90 | `0x0a68c97fc10e77ebe065a4959ae3e7e4896802b6` | DORMANT |
| 4 | 107.50 | `0x29664e652ca8f8f2d95de3b33cc0ae7247fc0aa9` | DORMANT |
| 5 | 103.35 | `0xcafbf7952763c7237d2848a553e3146cbdd08602` | DORMANT |
| 6 | 95.00 | `0x062c5432107e3b9ad924512209a7468b5c200fcd` | DORMANT |
| 7 | 81.00 | `0x60c7db709ebf1c3cf01057245eaaf79c6796e4e4` | DORMANT |
| 8 | 75.00 | `0x44874658340fa4ebe399546841319655fb606a45` | DORMANT |
| 10 | 62.00 | `0x59f4509017edcccc365881ba6d661a3bc63ebb79` | DORMANT |
| 11 | 60.00 | `0x555428363d00b92205216c61db67cecbff7554b2` | DORMANT |
| 12 | 60.00 | `0xa8924506f77f1976bf5b12b0ab819c9eb139b704` | DORMANT |
| 13 | 59.00 | `0xa8e0681d9e870b457084fb9223f13401b20b4ad0` | DORMANT |
| 14 | 58.88 | `0x302864d6bb190109a4a4fe734e2bac3a3a27bb57` | DORMANT |
| 15 | 58.74 | `0xb8b93fc7461286c34d8d7493a32b3a1e31a0b8fe` | DORMANT |
| 16 | 57.99 | `0xb0906862b2197ed783cf3c74236f0b98ecfbe91b` | DORMANT |
| 17 | 55.00 | `0xac208f311616bfd35489a4db58122f380b7abc79` | DORMANT |
| 18 | 55.00 | `0x2f2f237d2e655cc0a6f6fef761e5aef13087e71f` | DORMANT |
| 20 | 50.00 | `0xd3d7e517eac437931cd06672198ff55fbcc0496d` | DORMANT |
| 21 | 50.00 | `0x6ec30fd91a504aad948839b985c7263888b2ad68` | DORMANT |
| 22 | 45.00 | `0xad3dbf17e7460352adbb528420aa027cb2409597` | DORMANT |
| 24 | 40.90 | `0x066b4894be13ac0d49b24fc588668e428ec404e9` | DORMANT |
| 25 | 40.00 | `0x717541ecec745b1996a293a0e663f2aed2340f1a` | DORMANT |
| 26 | 39.00 | `0x4b17bb0d1f75636ea4c677377d29e86bae0038b6` | DORMANT |
| 27 | 38.00 | `0x0f8bd7b597c655869e58b9c1bcfa4ddfe590259d` | DORMANT |
| 29 | 33.00 | `0x9359301a9649b9fb9f29609848da3dbd7fe13fa1` | DORMANT |
| 30 | 32.89 | `0x7263a7c2cc2aec9710011c756fbc51dcfa31bb7c` | DORMANT |

(...and 17 more dormant addresses)

**Total ETH locked in dormant addresses: ~1,800 ETH (~$4.5M)**

---

## The "Lost Key" Forensic Theory

The fact that an address has nonce=0 but received pendingWithdrawals from
CryptoPunks is highly unusual. Possible explanations:

### 1. Cold Storage Generated for Sale (most likely)

The original owner generated a fresh address in 2017-2018 specifically to
receive their CryptoPunk sale proceeds. They then:
- Listed the punk for sale via `offerPunkForSale(idx, price)` (used a hot wallet)
- Buyer called `buyPunk(idx)` paying ETH → contract credited `pendingWithdrawals[seller]`
- Seller forgot to call `withdraw()` on the cold wallet
- Cold wallet's keystore was lost / hardware wallet died / paper backup destroyed

### 2. Bid Refunds to Forgotten Wallets

Address X bid on a punk via `enterBidForPunk` (hot wallet, used). Their bid
was outbid → refunded to `pendingWithdrawals[bidder]`. Bidder forgot.

### 3. Smart Contract Wallets That Selfdestructed

Some addresses may have been smart-contract wallets (Gnosis Safe early
versions, custom multisigs) that self-destructed. The address now has
no code and nonce = 0 (because nonce was reset on self-destruct in some
old EVM versions).

---

## How These Funds Could Be Recovered

### Path A: Original owner finds their old wallet ⭐
The most likely path. If you owned and sold a CryptoPunk between 2017-2025,
and never withdrew the proceeds, **your old wallet may be in this list**.

Actions:
1. Check old hardware wallets, paper wallets, keystore JSON files
2. Cross-reference your old addresses against the list above
3. If match found, sign a transaction calling `withdraw()` on
   `0xb47e3cd837dDF8e4c57F05d70Ab865de6e193BBB`

### Path B: Cracking the private key (impossible)
The 43 dormant addresses are random Ethereum addresses (not vanity-pattern,
not Profanity-tool generated). Cracking a random 256-bit ECDSA key requires
~2^128 operations - cryptographically infeasible.

### Path C: Quantum computing (future, not yet)
A sufficiently powerful quantum computer running Shor's algorithm could
derive private keys from public keys. As of May 2026, this is not yet
practical. Estimated 5-15 years until quantum threat materializes.

### Path D: Address reverse-engineering from old-event activity
If a bid was placed (`enterBidForPunk` event) by one of these addresses,
the transaction was signed and broadcast publicly. The signature contains
the public key. From the public key and signature, ECDSA reveals the
private key only if there are TWO signatures with the same nonce
(nonce-reuse attack). Modern Ethereum wallets use deterministic nonces
(RFC 6979) so this is unlikely - but old custom wallets may have leaked.

---

## Comparison with Other Recovery Pools

| Pool | ETH | # Addresses | Recoverable Path |
|------|----:|------------:|------------------|
| **CryptoPunks V2 pendingWithdrawals** | 2,247 | 94 | Each holder's private key |
| **CryptoPunks V1 pendingWithdrawals** | ~4 | 18 | Same |
| EtherDelta v3 user balances | ~15,222 | ~30,000 | Each depositor's key |
| IDEX 1.0 user balances | ~16,168 | unknown | Same |
| WithdrawDAO | 81,914 | (token holders) | DAO tokens from 2016 |
| Friend.tech (Base) | 928 | (share holders) | Share holders' keys |

CryptoPunks is the **smallest pool but highest per-address** ($60K-$385K each
for top 10).

---

## Action Items for the User

1. **Generate a list of ALL Ethereum addresses you've ever used** (2016-2025)
2. **Run** [`check_my_addresses.py`](./check_my_addresses.py) **with that list**:
   ```bash
   echo "0xYourOldAddress1..." > my_addrs.txt
   echo "0xYourOldAddress2..." >> my_addrs.txt
   python3 check_my_addresses.py --file my_addrs.txt
   ```
3. **If you ever bought/sold a CryptoPunk**, search for the wallet you used.
   Check email history, old browsers, Mist wallet folders, hardware wallet
   export files.

Even if you don't think you own one of these addresses, it's worth checking
- many people forgot they used a separate "cold" wallet for their first
NFT sales in 2017-2018.

---

## Files Generated

- [`results/cryptopunks_pending.json`](./results/cryptopunks_pending.json) - 94 sellers + amounts
- [`results/cryptopunks_full_recoverable.json`](./results/cryptopunks_full_recoverable.json) - Full analysis with EOA/contract classification
- [`cryptopunks_pending_scan.py`](./cryptopunks_pending_scan.py) - Scanner code
- [`cryptopunks_full_analysis.py`](./cryptopunks_full_analysis.py) - This deep analysis
