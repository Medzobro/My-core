# مستحقاتي · Mustahaqati — scanner package

Read-only audit of stuck balances for a single EVM address, plus the research tooling it
grew out of. See the [root README](../README.md) for the full picture.

## Run the web app

```bash
pip install -r requirements.txt
uvicorn audit.server:app --host 0.0.0.0 --port 8010
```

- `GET /` — Arabic RTL interface
- `POST /api/audit` — `{"address": "0x..."}` → JSON report
- `GET /report/{address}` — shareable HTML report

## Run the engine directly

```python
import asyncio
from audit.engine import audit_address

report = asyncio.run(audit_address("0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045"))
print(report.totals)          # {'by_symbol': {...}, 'usd_total': ..., 'count': ...}
for finding in report.findings:
    print(finding.contract_name, finding.amount, finding.symbol)
    for step in finding.steps:
        print(" -", step["ar"])
```

## CLI

```bash
python lost_eth.py stats                 # database overview
python lost_eth.py scan 0xAddress        # legacy terminal scanner
python lost_eth.py discover 0xAddress    # derive contracts from your own tx history
python lost_eth.py airdrops 0xAddress    # unclaimed airdrop tokens
python lost_eth.py nfts 0xAddress        # NFT holdings
```

## Tests

```bash
pip install -r requirements-dev.txt pytest httpx ruff
pytest -q
```

44 tests, fully offline (fake JSON-RPC). CI runs lint, format check, tests and a Docker
build on Python 3.11–3.13.

## Data

`data/chains.json`, `data/contracts_multichain.json`, `data/tokens_multichain.json` are
plain JSON so every entry can be reviewed in a diff. Only contracts with a defined
`balance_check` are scanned by the audit engine:

| `balance_check` | Meaning |
|---|---|
| `etherdelta` | `tokens[token][user]` mapping (EtherDelta-style DEX) |
| `erc20_self` | `balanceOf(user)` on the contract itself (cTokens, gas tokens) |
| `erc20_holder` | balance of a *different* token that gates withdrawal (DAO) |
| `cryptopunks` | `pendingWithdrawals(address)` |

## Ethics

This package reads public state for an address you supply. It contains no tool for
taking over, draining or key-cracking someone else's contract. The research reports
(`FINAL_REPORT.md`, `HUNT_RESULTS.md`) explain why that path was abandoned — including the
result that **zero** contracts were freely drainable after ~31,000 simulations.
