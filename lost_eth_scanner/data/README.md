# Data Files

Input databases used by all scanners.

| File | Purpose | Size |
|------|---------|------|
| `chains.json` | RPC endpoints for 20 EVM chains (Ethereum + L2s + sidechains) | 20 chains |
| `contracts_multichain.json` | Master DB of 365 abandoned/dead contracts | 365 contracts |
| `contracts_airdrops.json` | Merkle airdrop claim contracts (UNI, ARB, OP, etc.) | 91 airdrops |
| `contracts_extra.json` | Failed bridges, rugged DeFi, exploited contracts (added in v4) | 172 contracts |
| `contracts.json` | Original (small) contract list - first version of the DB | 7 contracts |
| `tokens_multichain.json` | Common ERC-20 reference list per chain | various |

## Adding a new contract

Edit `contracts_multichain.json` and add an entry like:
```json
{
  "chain": "ethereum",
  "name": "My Found Contract",
  "address": "0x...",
  "category": "DEFI_INACTIVE",
  "deployed": "2021-04",
  "balance_check": "etherdelta",
  "withdraw_method": "withdraw(uint256)",
  "notes": "Why this is interesting"
}
```

Categories used:
- `USER_DEPOSITS` - DEX-style (depositor calls withdraw)
- `TOKEN_HOLDER` - holds another token (DAO, gas tokens)
- `BRIDGE_DEAD` / `BRIDGE_DEPRECATED` / `BRIDGE_EXPLOITED`
- `DEFI_INACTIVE` / `DEFI_DEAD` / `DEFI_EXPLOITED`
- `RUGPULL` - team disappeared with funds
- `MIXER_SANCTIONED` - Tornado Cash etc.
- `NFT_OLD` - old NFT marketplaces
- `DAO_INACTIVE` / `DAO_DEAD`
- `ICO_OLD` - 2017-2018 ICO contracts
- `AIRDROP_CLAIM` - merkle distributors
- `DEFUNCT` / `DEFUNCT_GAME` / `DEFUNCT_PONZI` / `DEFUNCT_SCAM`
