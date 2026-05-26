# 🏴‍☠️ CryptoPunks pendingWithdrawals — Final Verdict

> Comprehensive forensic analysis of the 2,247 ETH ($5.6M) unclaimed in CryptoPunks V2.

---

## TL;DR

After **deep analysis using verified RPCs**, the conclusion is:

| Category | Count | ETH | Recoverable? |
|----------|------:|----:|--------------|
| **Active wallets** (owners alive, just haven't claimed) | 88 | 2,105.58 | ✅ By owner only |
| **Truly dormant EOAs** (lost-key candidates) | 0 | 0 | — |
| **Contract holders** | 5 | 132.04 | ❌ See below |
| **Low-activity** | 2 | 1.30 | ✅ By owner only |
| **Already claimed since last scan** | 2 | (37.4) | (claimed by owner) |

**Total: 0 ETH recoverable by anyone other than the original owners.**

---

## The Contract Holders Investigation

The 5 contracts holding pendingWithdrawals were investigated in detail:

### Contract #1: `0xcafbf7952763c7237d2848a553e3146cbdd08602` — 103.35 ETH
**Type**: Gnosis Safe v1.4.1 (3-of-5 multisig)
**Implementation**: `0x41675c099f32341bf84bfc5382af534df5c7461a`
**Status**: Actively managed - 31 transactions executed
**Owners**:
- 4 of 5 owners are clearly active (high nonces, real balances)
- Threshold 3-of-5 means we'd need 3 owner keys to drain
- Verdict: NOT exploitable

### Contract #2: `0x47452c970e08bf7105c753b798536e685e042231` — 28.89 ETH
**Type**: Gnosis Safe v1.4.1 (3-of-7 multisig)
**Implementation**: `0x41675c099f32341bf84bfc5382af534df5c7461a`
**Status**: Actively managed - 13 transactions executed
**Owners**: All 7 owners are active EOAs with balances and many transactions
**Verdict**: NOT exploitable

### Contract #3: `0x3bb0fe1d19e1f10a457cd3d26cd0db78dfdd677e` — 0.8 ETH ⚠️
**Bytecode**: `0xef010063c0c19a282a1b52b07dd5a65b58948a07dae32b` (23 bytes)
**Status**: EOF-format invalid bytecode (`0xef01...` prefix is reserved per EIP-3540)
**Verdict**: PERMANENTLY STUCK - the EVM cannot execute this code. The 0.8 ETH
is locked forever. No recovery path exists, even for the original deployer.

### Contracts #4 and #5: 0 ETH each
**Status**: The pendingWithdrawals were already claimed before our scan.

---

## Why The Initial "43 Dormant Addresses" Finding Was Wrong

In our first analysis, 43 of top 50 addresses appeared to have `nonce=0` and
`balance=0`, suggesting lost-key wallets.

**This was incorrect.** The cause:

The asyncio scan used multiple RPCs in parallel. When `eth.llamarpc.com`,
`rpc.ankr.com`, and `cloudflare-eth.com` returned **stale/cached data**
showing `nonce=0` faster than `publicnode.com` returned correct data,
our async loop took the first response (stale).

Verified via cross-check:
- `publicnode.com`: `0x8be6ad79...` → nonce=205, balance=32.88 ETH (CORRECT)
- `ankr.com`: same address → nonce=0, balance=0 (STALE/WRONG)
- `cloudflare-eth.com`: same → nonce=0, balance=0 (STALE/WRONG)

**Lesson**: Always cross-check public RPC responses, especially for
historical state queries. publicnode.com is currently the most reliable
free Ethereum RPC for accurate state.

---

## The Final Answer

The 2,210 ETH unclaimed in CryptoPunks **all belongs to alive, active
owners** who simply haven't called `withdraw()` yet.

Common reasons they haven't:
- Small individual amounts vs gas cost (e.g., 1 ETH unclaimed but $50 gas to claim)
- Forgot they had it (sold a punk in 2017, never thought about it again)
- Lost track of which old wallet had the pending balance
- Decided to wait for a gas spike to drop

The fact that **2 addresses claimed their balance between our scans** confirms
the owners are alive and slowly claiming over time.

For US (or anyone other than the rightful owners), there is **no exploitation
path**:
- No contract bug in CryptoPunks V2
- No backdoor or admin override
- The Gnosis Safes holding pending balances are actively-managed multisigs
- The one truly stuck balance (0.8 ETH in EOF-format contract) is permanently
  locked — not even the original deployer can retrieve it

---

## What Could Help YOU

If you ever sold a CryptoPunk between 2017-2025:

1. Find every Ethereum address you used during that period (old MetaMask,
   Mist, hardware wallet exports, exchange withdrawal addresses)
2. Compare against [`results/cryptopunks_corrected.json`](./results/cryptopunks_corrected.json)
3. If your old address matches, recover with one transaction:
   ```bash
   # Just need the private key for the matching address
   python3 check_my_addresses.py --file my_addrs.txt
   ```

Top 30 addresses with active pending balances are listed in
[`CRYPTOPUNKS_DEEP_ANALYSIS.md`](./CRYPTOPUNKS_DEEP_ANALYSIS.md). The
addresses ARE active, so the original owners are using their wallets — they
just have an old un-withdrawn CryptoPunks balance.

---

## Files Generated

- [`cryptopunks_pending_scan.py`](./cryptopunks_pending_scan.py) - Initial scanner
- [`cryptopunks_full_analysis.py`](./cryptopunks_full_analysis.py) - First analysis (had RPC bug)
- [`cryptopunks_corrected_analysis.py`](./cryptopunks_corrected_analysis.py) - **Correct** analysis
- [`cryptopunks_contract_holders.py`](./cryptopunks_contract_holders.py) - Contract investigation
- [`cryptopunks_proxy_decode.py`](./cryptopunks_proxy_decode.py) - Bytecode disasm of proxy contracts
- [`cryptopunks_safe_analysis.py`](./cryptopunks_safe_analysis.py) - Gnosis Safe investigation

Results in [`results/`](./results/):
- `cryptopunks_pending.json` - 94 sellers + amounts (initial scan)
- `cryptopunks_corrected.json` - Verified state per address
- `cryptopunks_full_recoverable.json` - Combined view
