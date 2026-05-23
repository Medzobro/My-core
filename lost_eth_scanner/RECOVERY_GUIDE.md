# 💰 Recovery Guide — دليل استرداد ETH

> Step-by-step guide for recovering lost ETH from abandoned contracts.
> دليل عملي خطوة بخطوة لاسترداد ETH من العقود المهجورة.

---

## 🇸🇦 العربية

### الحقيقة المهمة أولاً

بعد فحص 365 عقد عبر 20 سلسلة:

✅ **ETH موجود فعلاً قابل للاسترداد** — لكن يحتاج مفتاح خاص لعنوان معيّن
❌ **ETH مجاني للجميع** = صفر (بسبب MEV bots)

### خطوة 1: تجميع عناوينك القديمة

ابحث في كل مكان ممكن:

| المصدر | ملاحظات |
|--------|---------|
| 📧 ايميلات قديمة | كثير من الناس حفظوا keystore JSON في ايميلهم |
| 💾 USB قديم | محافظ Mist, MyEtherWallet, MyCrypto |
| 🔐 hardware wallets | Trezor, Ledger - استخدم Live Wallet لمشاهدة العناوين |
| 📱 محافظ موبايل قديمة | MetaMask, imToken, Trust Wallet |
| 💻 ملفات keystore | عادة بصيغة UTC--*.json |
| 🏦 تاريخ منصات الصرف | Bittrex, Poloniex, Kraken (2017-2019) |
| 📸 سكرين شوت قديم | كثيراً ما يحوي عناوين |

### خطوة 2: فحص العناوين

#### الطريقة 1: عناوين فردية
```bash
cd lost_eth_scanner

# ضع عناوينك في ملف
echo "0xYourFirstAddress" > my_addrs.txt
echo "0xYourSecondAddress" >> my_addrs.txt

# فحص
python3 check_my_addresses.py --file my_addrs.txt
```

#### الطريقة 2: من عبارة استرداد (12/24 كلمة)

⚠️ **خطر! استخدم فقط على جهاز offline** (بدون انترنت)

```bash
pip install eth-account mnemonic

python3 hd_wallet_scanner.py --mnemonic "your twelve word seed phrase here" --n 50
```

سيقوم باشتقاق 200 عنوان من 4 مسارات HD معروفة:
- `m/44'/60'/0'/0/{i}` - MetaMask, MyEtherWallet, Trezor
- `m/44'/60'/{i}'/0/0` - Ledger Live
- `m/44'/60'/0'/{i}` - Ledger Legacy
- `m/0'/0/{i}` - Mist (محافظ قديمة 2014-2016)

### خطوة 3: السحب (لو وُجد رصيد)

#### CryptoPunks pendingWithdrawals
```python
from web3 import Web3

w3 = Web3(Web3.HTTPProvider('https://ethereum-rpc.publicnode.com'))

# V2 (الحالي)
contract_addr = '0xb47e3cd837dDF8e4c57F05d70Ab865de6e193BBB'
# V1 (القديم)
# contract_addr = '0x6BA6f2207e343923BA692e5Cae646Fb0F566DB8D'

abi = [{'name': 'withdraw', 'type': 'function', 'inputs': [], 'outputs': []}]
contract = w3.eth.contract(address=contract_addr, abi=abi)

acct = w3.eth.account.from_key('YOUR_PRIVATE_KEY')
tx = contract.functions.withdraw().build_transaction({
    'from': acct.address,
    'gas': 100000,
    'gasPrice': w3.eth.gas_price,
    'nonce': w3.eth.get_transaction_count(acct.address),
})
signed = acct.sign_transaction(tx)
tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
print(f'Sent: {tx_hash.hex()}')
```

#### EtherDelta / ForkDelta v3 / IDEX 1.0 / Token.Store
```python
# ABI: withdraw(uint256 amount) for ETH withdrawal
abi = [{'name': 'withdraw', 'type': 'function',
         'inputs': [{'name':'amount','type':'uint256'}], 'outputs': []}]

# اسحب الكمية كاملة (شف من check_my_addresses.py)
amount_wei = 1234567890123456789  # ضع الرصيد بالـ wei

contract = w3.eth.contract(address='0x8d12A197cB00D4747a1fe03395095ce2A5CC6819', abi=abi)
tx = contract.functions.withdraw(amount_wei).build_transaction({...})
```

#### WithdrawDAO (لو عندك DAO tokens من 2016)
```python
# 1. أولاً approve مبلغ DAO الذي عندك
dao_token = '0xbb9bc244d798123fde783fcc1c72d3bb8c189413'
withdraw_dao = '0xbf4ed7b27f1d666546e30d74d50d173d20bca754'

# 2. ثم استدعِ withdraw() على WithdrawDAO
# 100 DAO = 1 ETH
```

---

## 🇬🇧 English

### Important Reality First

After scanning 365 contracts across 20 chains:

✅ **Recoverable ETH does exist** — but requires the private key for a specific address
❌ **"Free" ETH for anyone** = zero (MEV bots drain it instantly)

### Step 1: Gather your old addresses

Search everywhere possible:

| Source | Notes |
|--------|-------|
| 📧 Old emails | Many people emailed themselves keystore JSON files |
| 💾 Old USB drives | Mist, MyEtherWallet, MyCrypto wallets |
| 🔐 Hardware wallets | Trezor, Ledger - use their Live app to see addresses |
| 📱 Old mobile wallets | MetaMask, imToken, Trust Wallet |
| 💻 Keystore files | Usually named UTC--*.json |
| 🏦 Exchange history | Bittrex, Poloniex, Kraken (2017-2019) |
| 📸 Old screenshots | Often contain addresses |

### Step 2: Scan addresses

#### Method 1: Individual addresses
```bash
cd lost_eth_scanner
echo "0xYourFirstAddress" > my_addrs.txt
echo "0xYourSecondAddress" >> my_addrs.txt
python3 check_my_addresses.py --file my_addrs.txt
```

#### Method 2: From BIP-39 seed phrase
**⚠️ DANGER! Only run on an air-gapped (offline) machine.**

```bash
pip install eth-account mnemonic
python3 hd_wallet_scanner.py --mnemonic "your twelve word seed phrase" --n 50
```

Derives 200 addresses across 4 HD paths.

### Step 3: Withdraw (if balance found)

See Arabic section above for code examples — same code works in English.

---

## 📋 Checklist

- [ ] Searched email for "keystore" / "wallet" / "ethereum" / "JSON"
- [ ] Checked all old USB drives + cloud backups
- [ ] Reviewed hardware wallet derivation paths
- [ ] Listed every Ethereum address used 2016-2020
- [ ] Ran `check_my_addresses.py --file my_addrs.txt`
- [ ] (If found) Built withdrawal transaction with correct nonce
- [ ] Verified gas estimate before broadcasting
- [ ] Signed transaction with PRIVATE KEY (never share)
- [ ] Broadcast and confirmed on-chain

---

## 🆘 Specific Recovery Paths

### Path A: You sold a CryptoPunk between 2017-2025 but never withdrew
The 94 addresses in [`results/cryptopunks_pending.json`](./results/cryptopunks_pending.json)
have unclaimed ETH from accepted bids. If your old address matches one of those:
total possible recovery: 0.5 to 153.45 ETH per address.

### Path B: You used EtherDelta/ForkDelta in 2017-2018
Estimated 30,000+ addresses still have ETH/tokens stored in
`0x8d12A197cB00D4747a1fe03395095ce2A5CC6819`. Use `tokens(0x0, you)` to check.

### Path C: You participated in The DAO in May 2016
DAO tokens from the original ICO can still be redeemed at WithdrawDAO
for 1 ETH per 100 DAO. 81,914 ETH still in the contract.

### Path D: You used IDEX 1.0
ETH and tokens still recoverable via standard `withdraw(uint256)` and
`withdrawToken(address,uint256)`.

### Path E: You held cETH in Compound v1
cETH is redeemable for ETH via `redeem(uint256)`. The original
Compound v1 cETH contract: `0x3FDA67f7583380E67ef93072294a7fAc882FD7E7`.

---

## ⚠️ Security Warnings

1. **Never share your private key** with anyone, including support.
2. **Never type your seed phrase on an internet-connected device**.
3. The recovery scripts here only **read** from blockchain — they do NOT
   transmit your keys anywhere.
4. Always verify contract addresses on Etherscan before broadcasting.
5. Use a fresh fully-funded gas account if you're worried about your
   keystore being exposed.

---

## 🤔 No Funds Found?

If `check_my_addresses.py` returns nothing, possible reasons:

- **Your address didn't deposit to the listed contracts** → still try other DEXes
- **You're using the wrong address** → derive more addresses with `--n 100`
- **Your contracts are on chains other than Ethereum** → try Polygon, BSC, Arbitrum
- **Your funds were already drained** → check Etherscan tx history of the address
- **You actually never had funds there** → unfortunately, no recovery possible

---

## 📞 Need Help?

Open an issue on the GitHub repo with:
- Which step failed
- Output from the scanner (NEVER include private keys or seed phrases)
- Which contract you're trying to recover from
