# Forgotten Contracts Database

The scanner currently tracks **107 contracts** across 8 chains. See `contracts_multichain.json` for the full list.

## By Chain

| Chain | Count | Examples |
|-------|-------|----------|
| Ethereum | 57 | IDEX 1.0, EtherDelta v1/v2/v3, Token.Store, WithdrawDAO, Compound v1, MakerDAO SAI, OpenSea v1/v2, Tornado Cash |
| Arbitrum | 12 | GMX V1, Camelot V2/V3, SushiSwap, Hop, Trader Joe, Vela, Dopex |
| Polygon | 9 | QuickSwap V2/V3, Aave V2, PoS Bridge, SushiSwap, Iron Bank |
| Optimism | 8 | Velodrome V1/V2, Synthetix, Hop, Across, Beethoven X |
| BSC | 8 | PancakeSwap V2/V3, Venus, BiSwap, BurgerSwap, Bunny |
| Base | 6 | BaseSwap, Aerodrome, RocketSwap, Friend.tech |
| zkSync | 4 | SyncSwap, Mute.io, Maverick, zkLend |
| Linea | 3 | LineaSwap, Velocore, HorizonDEX |

## By Category

| Category | Count | Description |
|----------|-------|-------------|
| `USER_DEPOSITS` | 63 | Original depositor can withdraw (most cases) |
| `DEPRECATED` | 33 | Old protocol still functional for legacy users |
| `FROZEN` | 6 | Permanently locked (Parity multisigs, original DAO) |
| `TOKEN_HOLDER` | 4 | Holders of specific token can claim (WithdrawDAO, GST2, CHI, SAI) |
| `OWNED` | 1 | Only contract owner can withdraw |

## Notable Contracts

### Parity Frozen (444,615 ETH locked forever)

| Address | Owner | Balance |
|---------|-------|---------|
| `0x3bfc20f0b9afcace800d73d2191166ff16540258` | Polkadot Foundation | 306,276 ETH |
| `0x376c3e5547c68bc26240d8dcc6729fff665a4448` | Iconomi | 114,939 ETH |
| `0xc7cd9d874f93f2409f39a95987b3e3c738313925` | Musiconomi | 16,475 ETH |
| `0xdb0e7d784d6a7ca2cbda6ce26ac3b1bd348c06f8` | Unknown | 6,925 ETH |

### WithdrawDAO (81,914 ETH still claimable)

`0xbf4ed7b27f1d666546e30d74d50d173d20bca754`

Anyone holding original DAO tokens (`0xbb9bc244d798123fde783fcc1c72d3bb8c189413`) can claim 1 ETH per 100 DAO tokens via the `withdraw()` function. Active withdrawals as of 2026.

### IDEX 1.0 (16,168 ETH user deposits)

`0x2a0c0DBEcC7E4D658f48E01e3fA353F44050c208`

Users who deposited to the original IDEX exchange (2017-2020) can withdraw via `withdraw(address,uint256)` after the inactivity period.

## Adding a new contract

Edit `contracts_multichain.json`:

```json
{
  "chain": "ethereum",
  "name": "My Old Protocol",
  "address": "0x...",
  "balance_check": "etherdelta",
  "withdraw_method": "withdraw(address,uint256)",
  "category": "USER_DEPOSITS",
  "deployed": "2018-01"
}
```

`balance_check` types:
- `etherdelta`: `balanceOf(token, user)` selector `0xf7888aec`
- `erc20_self`: `balanceOf(user)` on the contract itself
- `erc20_holder`: User holds another token (set `balance_check_token`)
