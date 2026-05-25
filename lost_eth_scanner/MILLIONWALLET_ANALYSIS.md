# MillionWallet / Million.Money Forensic Analysis

> Comprehensive analysis of the famous Ethereum Ponzi/MLM scheme
> known as **Million.Money** (sometimes referred to as "MillionWallet").

---

## Contract Identification

Two contracts deployed by the same operator:

| Version | Address | Code Size | Status |
|---------|---------|----------:|--------|
| V1 (old) | `0x4Dcf60F0cb42c22Df36994CCBebd0b281C57003A` | 8,826 bytes | Migrated |
| **V2 (current)** | **`0xbCF935D206Ca32929e1b887a07Ed240f0D8CCD22`** | **7,037 bytes** | Dormant |

**Owner Wallet**: `0xb19da4fd9f9a73a5a564c66d229b1e7219e8bdbe` (EOA)

Website: https://million.money (Russian-language MLM portal)

---

## Current State (May 2026)

| Metric | V1 | V2 | Owner |
|--------|---:|---:|------:|
| ETH Balance | **0.000000** | **0.000000** | 0.000114 |
| Nonce | 1 | 1 | 508 |
| Last Activity | None recent | None recent | Active |
| Total Users Registered | 1,794 | **697,938** | -- |

**NO ETH currently stuck in either contract.**

---

## How The Scam Works (From Verified Source Code)

```solidity
contract MillionMoney {
    address public ownerWallet;
    mapping (address => UserStruct) public users;
    uint public currUserID = 0;

    // 10 levels with increasing prices
    LEVEL_PRICE[1]  = 0.03 ether;
    LEVEL_PRICE[2]  = 0.05 ether;
    LEVEL_PRICE[3]  = 0.1  ether;
    LEVEL_PRICE[4]  = 0.4  ether;
    LEVEL_PRICE[5]  = 1.0  ether;
    LEVEL_PRICE[6]  = 2.5  ether;
    LEVEL_PRICE[7]  = 5.0  ether;
    LEVEL_PRICE[8]  = 10.0 ether;
    LEVEL_PRICE[9]  = 20.0 ether;
    LEVEL_PRICE[10] = 40.0 ether;

    // PASSTHROUGH PONZI: incoming ETH immediately forwarded
    function regUser(uint _referrerID) public payable { ... }
    function buyLevel(uint _level) public payable { ... }

    // CRITICAL: There is NO withdraw() function!
    // There is NO rescue() / sweep() / admin function!
    // There is NO selfdestruct, no upgrade path!
    // There is NO pendingWithdrawals mapping!
}
```

### Where The Money Goes

When User X pays 0.03 ETH:
```
User X --0.03 ETH--> Million.Money contract
                            |
                            +--> Immediately forwards to upline referrer
                                  (or to ownerWallet if no referrer is "free")
```

The contract is a **passthrough** -- it never accumulates a balance.

---

## Recoverability Verdict

### Zero ETH Recoverable

| Why | Explanation |
|-----|-------------|
| Contract balance = 0 | Both V1 and V2 hold zero ETH |
| Passthrough design | Funds never accumulate |
| No withdraw function | No way for users to claim from the contract |
| No admin recovery | Even the owner cannot retrieve user funds |
| No upgrade path | Cannot deploy a "patch" to add recovery |
| No selfdestruct | Cannot destroy and reclaim |

### Where Did The Money Go?

For each of the 697,938 users who paid in:
- Their ETH was immediately split among:
  - Their upline referrers (up to 7 levels)
  - The ownerWallet (whenever the level was "lost")
- The owner address `0xb19da4fd...` historically received millions of dollars in fees
- That ETH is now distributed across many wallets

---

## Summary

This analysis was conducted in response to a user request to analyze "MillionWallet"
(traced to Million.Money contract). The contract holds **zero ETH** by design --
it's a Ponzi passthrough that immediately forwards all incoming ETH to upline
referrers. No exploit path exists. 697,938 victims cannot recover from the
contract; their ETH is in their referrers' wallets.

For potential victims: legal/regulatory channels are the only recovery option,
similar to the Forsage prosecution (founder extradited from Thailand 2026).
