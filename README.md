# Mustahaqati · مستحقاتي

**A read-only audit that finds money you forgot on-chain.**

You deposited on a DEX that shut down. You sold a CryptoPunk and never withdrew the
proceeds. You still hold gas tokens from 2020. This project checks one address against a
database of known stuck-fund contracts across EVM chains and returns a report with the
exact recovery steps — where to click, which function to call, which argument goes where.

It never asks for a private key. It never signs anything. It only reads public chain state.

```
$ curl -s -X POST localhost:8010/api/audit -H 'content-type: application/json' \
    -d '{"address":"0x8be6ad79f67d1b76eba486b0ef4fd2c9bd1cd067"}' | jq '.verdict_ar'
"وُجد 1 رصيداً قابلاً للاسترداد: 153.45 ETH (~$306,900)."
```

---

## What it actually covers

Honest scope, because the interesting part of this repo is what it *refuses* to claim.

| Contract | What is checked | Recovery |
|---|---|---|
| CryptoPunks Marketplace | `pendingWithdrawals(address)` | `withdraw()` |
| ForkDelta / EtherDelta v3 | `tokens[token][user]` for ETH + 39 tokens | `withdraw` / `withdrawToken` |
| IDEX 1.0 | same mapping | `withdraw(address,uint256)` |
| Token.Store | same mapping | `withdraw(address,uint256)` |
| EtherDelta v1 / v2, Saturn | same mapping | legacy |
| Compound v1 cETH / cDAI | `balanceOf(address)` | `redeem(uint256)` |
| WithdrawDAO (The DAO) | DAO token balance | `approve` then `withdraw()` |
| GasToken2 / CHI | token balance | `free(uint256)` |
| Old SAI | token balance | deprecated, no path |

13 contracts on Ethereum mainnet, one address, ~250 RPC calls, ~3 seconds. The legacy CLI
also carries 20 chain configurations for its wider (non-recovery) scans.

Anything outside that table is **not** covered, and the report says so instead of guessing.

## What it does not do

- It does not take over, drain, or "rescue" contracts you do not own.
- It does not scan other people's wallets to build target lists.
- It does not crack keys, replay leaked secrets, or probe uninitialised proxies.

That entire class of tooling was deliberately removed from this repository — see
[`lost_eth_scanner/FINAL_REPORT.md`](lost_eth_scanner/FINAL_REPORT.md) for why: after
~31,000 RPC simulations over 365 contracts, the number of genuinely unguarded pools was
**zero**. There is no free money down that road, only legal exposure.

## Quick start

```bash
git clone https://github.com/Medzobro/My-core
cd My-core/lost_eth_scanner
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

uvicorn audit.server:app --host 0.0.0.0 --port 8010
# open http://localhost:8010
```

CLI and API work without a browser:

```bash
python - <<'PY'
import asyncio
from audit.engine import audit_address
print(asyncio.run(audit_address("0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045")).to_dict()["totals"])
PY
```

## Architecture

```
lost_eth_scanner/
├── core/
│   ├── rpc.py        # JSON-RPC: endpoint rotation, retry/backoff, SQLite TTL cache
│   ├── pricing.py    # ETH→USD, two feeds, cached, degrades to None
│   └── util.py       # ABI encoding, address validation, formatting
├── audit/
│   ├── engine.py     # address → Report (13 checks + native balances)
│   ├── guide.py      # bilingual recovery steps per contract
│   ├── render.py     # server-rendered, shareable HTML report
│   ├── server.py     # FastAPI: /, /api/audit, /report/{addr}, /health
│   └── static/       # RTL dark UI (Cairo, no framework, ~20KB)
├── data/             # chains, contracts, tokens (plain JSON, reviewable)
├── tests/            # 44 tests, all offline (fake RPC)
├── discovery.py      # derive contracts from your own tx history
└── bytecode_analyzer.py  # selector/opcode/proxy forensics
```

Design notes:

- **Reverts are answers, transport errors are failures.** The engine counts them
  separately, so the report can show a real coverage percentage instead of silently
  treating a dead RPC as "no balance".
- **Cache by (chain, method, params).** `eth_getCode` lives 7 days, `eth_call` 2 minutes.
  Warm scans are ~20× faster.
- **The UI never builds HTML from data.** Dynamic text goes through `textContent`;
  server-rendered pages escape every value. Both paths are tested.

## API

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/api/audit` | `{"address": "0x..", "include_native": true}` → JSON report |
| `GET` | `/report/{address}` | shareable HTML report |
| `GET` | `/health` | liveness + cache counters |
| `GET` | `/api/stats` | aggregate counters |

Rate limit: 20 audits per IP per 5 minutes. Reports are cached 10 minutes in-process.

## Testing

```bash
pip install -r requirements-dev.txt pytest ruff httpx
pytest -q                     # 44 passed, no network
ruff check lost_eth_scanner/core lost_eth_scanner/audit lost_eth_scanner/tests
```

The suite covers decimal handling, difficulty mapping, the CryptoPunks selector, totals,
HTML escaping (XSS), HTTP status codes, and the SQLite cache. CI runs it on 3.11–3.13.

## Safety

- No key material is collected, stored, or transmitted. There is no field for it.
- The only writes are to a local SQLite cache file.
- Every recovery step points at Etherscan's *Write Contract* tab: you sign in your own
  wallet, from your own machine.
- Any "recovery service" that asks for an upfront fee or your seed phrase is a scam.

## Research history

This repo started as a hunt for recoverable ETH in abandoned contracts. The findings are
kept because negative results are results:

- `lost_eth_scanner/FINAL_REPORT.md` — what is recoverable, who owns it, what is locked forever
- `lost_eth_scanner/HUNT_RESULTS.md` — per-contract analysis (Parity, DAO, IDEX, EtherDelta)
- `analysis/IDEX_1.0_FULL_REPORT.md` — 400-line forensic deep dive
- `bug_bounty_kit/` — a 30-day plan for earning legally in Web3 security instead

## License

MIT — see [LICENSE](LICENSE).

---

## بالعربية

**مستحقاتي**: فحص للقراءة فقط يكشف الأموال التي تركتها على السلسلة — أرصدة في منصات
تداول أُغلقت، مبالغ بيع NFT لم تُسحب، توكنات غاز قديمة.

- لا يطلب مفتاحك الخاص، ولا يوقّع أي معاملة، ولا يعدّل أي عقد.
- يغطي 13 عقداً معروفاً على Ethereum، ويقول بصراحة ما لم يفحصه.
- تقرير عربي/إنجليزي بخطوات الاسترداد، ورابط قابل للمشاركة.
- أُزيلت من المشروع كل الأدوات التي تستهدف عقود الآخرين؛ تقرير المشروع يشرح السبب بالأرقام.
