# CLI Reference

The Master CLI `lost_eth.py` provides 10 subcommands for the entire toolkit.

## Subcommands

### `scan`
Scan one or more addresses for stuck balances across all chains.

```bash
python3 lost_eth.py scan 0xAddr1 [0xAddr2 ...]
  --chains ethereum,arbitrum  # filter chains
  --concurrency 100           # max simultaneous RPCs
  --include-native            # also include direct wallet balances
  --json results.json         # save output
  --watch                     # repeat scan periodically
  --interval 60               # watch interval in seconds
```

### `airdrops`
Check holdings against 20+ historical airdrops.

```bash
python3 lost_eth.py airdrops 0xAddr [0xAddr2 ...]
```

### `nfts`
Check holdings against 33 top NFT collections.

```bash
python3 lost_eth.py nfts 0xAddr
```

### `monitor`
Continuous monitoring with diff-detection.

```bash
python3 lost_eth.py monitor 0xAddr1 0xAddr2 \
  --interval 300 \
  --webhook https://discord.com/api/webhooks/... \
  --chains ethereum
```

### `hunt`
Forensic classification of any contract.

```bash
python3 lost_eth.py hunt 0xCONTRACT [0xCONTRACT2 ...]
```

If no addresses provided, runs against the curated dead contracts DB.

### `withdraw`
Generate raw transaction data for offline signing.

```bash
python3 lost_eth.py withdraw \
  0x2a0c0DBEcC7E4D658f48E01e3fA353F44050c208 \
  0x0000000000000000000000000000000000000000 \
  11616394896330848
```

### `api`
Start the FastAPI REST server.

```bash
python3 lost_eth.py api
  --host 0.0.0.0
  --port 8000
```

Then visit `http://localhost:8000/docs` for interactive Swagger.

### `hd`
Bulk scan many addresses (HD wallet derivation use case).

```bash
python3 lost_eth.py hd 0xAddr1 0xAddr2 ...
python3 lost_eth.py hd --addresses-file wallets.txt
```

### `stats`
Show database statistics.

```bash
python3 lost_eth.py stats
```

## Direct Tools

For advanced use cases, the underlying tools can be called directly:

```bash
python3 scanner_v2.py 0xAddr --concurrency 80
python3 discovery.py 0xAddr --include-l2
python3 bytecode_analyzer.py 0xCONTRACT --chain arbitrum
python3 storage_db.py stats
python3 storage_db.py history 0xAddr
python3 telegram_bot.py    # requires LOST_ETH_BOT_TOKEN env var
```
