# Supported Airdrops

The airdrop checker scans an address against these historical airdrops to detect held tokens (claimed or unclaimed).

| Airdrop | Date | Chain | Token Address | Notes |
|---------|------|-------|---------------|-------|
| Uniswap UNI | 2020-09 | Ethereum | `0x1f9840a85d5af5bf1d1762f925bdaddc4201f984` | 400 UNI per address that used Uniswap pre-Sep 2020 |
| ENS DAO | 2021-11 | Ethereum | `0xC18360217D8F7Ab5e7c516566761Ea12Ce7F9D72` | Required .eth name registration |
| Optimism OP (R1) | 2022-05 | Optimism | `0x4200000000000000000000000000000000000042` | Bridging + DAO voting |
| Optimism OP (R2) | 2023-02 | Optimism | `0x4200...0042` | Continued participation |
| Arbitrum ARB | 2023-03 | Arbitrum | `0x912CE59144191C1204E64559FE8253a0e49E6548` | Usage points pre-Feb 2023 |
| 1inch INCH | 2020-12 | Ethereum | `0x111111111117dc0aa78b770fa6a738034120c302` | 4+ trades or 1 trade > $20 |
| dYdX DYDX | 2021-09 | Ethereum | `0x92D6C1e31e14520e676a687F0a93788B716BEff5` | Active trading pre-Aug 2021 |
| LooksRare LOOKS | 2022-01 | Ethereum | `0xf4d2888d29D722226FafA5d9B24F9164c092421E` | NFT trading pre-2022 |
| Hop HOP | 2022-05 | Ethereum | `0xc5102fe9359fd9a28f877a67e36b0f050d81a3cc` | Bridge usage |
| Stargate STG | 2022-03 | Ethereum | `0xaf5191b0de278c7286d6c7cc6ab6bb8a73ba2cd6` | Bridge usage |
| Blur BLUR | 2023-02 | Ethereum | `0x5283D291DBCF85356A21bA090E6db59121208b44` | NFT trading on Blur |
| Aevo AEVO | 2024-03 | Ethereum | `0xb528edBef013aff855ac3c50b381f253aF13b997` | Derivatives trading |
| Wormhole W | 2024-04 | Ethereum | `0xB0fFa8000886e57F86dd5264b9582b2Ad87b2b91` | Bridge usage |
| StarkNet STRK | 2024-02 | Ethereum | `0xCa14007Eff0dB1f8135f4C25B34De49AB0d42766` | Bridge to claim on L2 |
| LayerZero ZRO | 2024-06 | Ethereum | `0x6985884C4392D348587B19cb9eAAf157F13271cd` | Bridge usage |
| Ethena ENA | 2024-04 | Ethereum | `0x57e114B691Db790C35207b2e685D4A43181e6061` | sUSDe holders |
| Etherfi ETHFI | 2024-03 | Ethereum | `0xFe0c30065B384F05761f15d0CC899D4F9F9Cc0eB` | LST stakers |
| Renzo REZ | 2024-04 | Ethereum | `0x3B50805453023a91a8bf641e279401a0b23FA6F9` | LRT stakers |
| EigenLayer EIGEN | 2024-10 | Ethereum | `0xec53bF9167f50cDEB3Ae105f56099aaaB9061F83` | Restakers |

## Adding a new airdrop

Edit `airdrop_checker.py`'s `AIRDROPS` list:

```python
{
    'name': 'Project XYZ',
    'date': '2025-01',
    'chain': 'ethereum',
    'token': '0x...',
    'token_decimals': 18,
    'token_symbol': 'XYZ',
    'note': 'Eligibility criteria description.',
}
```
