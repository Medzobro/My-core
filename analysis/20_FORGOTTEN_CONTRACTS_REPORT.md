# 🔬 تحليل forensic شامل — 20 عقد منسي ($20M ETH)

> فحص deep-dive لـ20 عقد بأرصدة مؤكدة من RPC مباشر
> الإجمالي: **8,050 ETH (~$20M USD)**
> التاريخ: مايو 2026

---

## 📊 الملخص التنفيذي

| الفئة | عدد العقود | إجمالي ETH | USD |
|-------|-----------|-----------|-----|
| 2020-2022 DeFi/DEX | 13 | 4,148 | $10.4M |
| Fomo3D Family (2018) | 6 | 4,067 | $10.2M |
| Token Old (BitConnect2) | 1 | 14.78 | $37K |
| **المجموع** | **20** | **~8,050** | **~$20M** |

**التحقق من البيانات:**
- ✅ كل الأرصدة محققة عبر RPC مباشر (publicnode.com)
- ✅ 19/20 عقد verified على Sourcify (مصدر متاح)
- ✅ 1 فقط بـSELFDESTRUCT (SwissCrypto)
- ⚠️ 13/20 بدون public `owner()` function
- ⚠️ 7/20 بـpublic owner

---

## 🎯 الفئة 1: Old WETH (1,514 ETH — الأكبر فردياً)

**العنوان:** `0xECF8F87f810EcF450940c9f60066b4a7a501d6A7`

### معلومات أساسية
| الحقل | القيمة |
|-------|--------|
| تاريخ النشر | **12 يونيو 2016** (~10 سنوات!) |
| الرصيد | 1,513.94 ETH |
| Code size | 2,565 bytes |
| name() | (empty bytes32) |
| symbol() | (empty bytes32) |
| decimals() | 1 (غريب — الـWETH العادي =18) |
| totalSupply() | يطابق الرصيد بالضبط (1:1 backing) |
| Sourcify | ❌ غير متحقق |
| Events ever | **0** (لم يصدر حدث واحد!) |

### الدوال المكتشفة في الـbytecode
```
✅ totalSupply()
✅ balanceOf(address)
✅ transfer(address,uint256)
✅ transferFrom(address,address,uint256)
✅ approve(address,uint256)
✅ allowance(address,address)
✅ deposit()
✅ withdraw(uint256)
```

### تحليل الاسترداد
- ✅ **WETH-style design**: حاملي الـtoken يقدرون يستدعون `withdraw(amount)` لاسترجاع ETH
- ❌ **0 events منذ 2016**: لا يمكن enumerate الـholders عبر event scanning
- ❌ **Sourcify غير متحقق**: لا source code
- ⚠️ **Holders غير معروفين**: لا طريقة لمعرفة من يملك الـtokens

**الفرضية:** المُنشئ نقل 1,514 ETH عبر `deposit()` ولم يستردها، أو أعطى الـtokens لمحفظة مفقودة.

**الاسترداد ممكن لـ:** فقط من يملك private key لمحفظة فيها WETH balance في العقد.

---

## 🎲 الفئة 2: Fomo3D Family (2018 Pyramid Games)

### الـ7 عقود مع أسعارها الحالية

| العقد | الرصيد | totalSupply | buyPrice | sellPrice | Fee% |
|-------|--------|-------------|----------|-----------|------|
| **PoWH3D (P3D)** | 2,091.55 ETH | 354,808 P3D | 0.003903 | 0.003193 | 18.2% |
| **GandhiJi (IND)** | 663.57 ETH | 183,307 IND | 0.002016 | 0.001650 | 18.2% |
| **BitConnect2 (BC2)** | 14.78 ETH | 25,968 BC2 | 0.000571 | 0.000467 | 18.2% |
| Fomo3D Long (F3D) | 1,117.39 ETH | (different model) | - | - | - |
| Fomo3D Short | 76.95 ETH | - | - | - | - |
| Fomo3D Quick | 84.50 ETH | - | - | - | - |
| ReadyPlayerONE | 24.54 ETH | - | - | - | - |

### آلية الـPyramid (مصدر مفتوح)

```solidity
// PoWH3D source (verified Sourcify)
function withdraw() onlyStronghands() public {
    address _customerAddress = msg.sender;
    uint256 _dividends = myDividends(false);
    payoutsTo_[_customerAddress] += (int256)(_dividends * magnitude);
    _dividends += referralBalance_[_customerAddress];
    referralBalance_[_customerAddress] = 0;
    _customerAddress.transfer(_dividends);
}

modifier onlyStronghands() {
    address _customerAddress = msg.sender;
    require(myDividends(true) > 0);  // يجب أن تملك dividends!
    _;
}
```

### اقتصاديات الـArbitrage

**السؤال:** هل يمكن شراء P3D رخيصاً واسترداد dividends؟

| المتغير | القيمة |
|---------|--------|
| Avg ETH backing per P3D | **0.005895 ETH/token** |
| Contract buyPrice | 0.003903 ETH (دفعة منك) |
| Contract sellPrice | 0.003193 ETH (إلى الـcontract) |
| فرق buy/sell | **18.2% loss** على round-trip |

### نتيجة فحص DEXs
**❌ لا يوجد Uniswap V2 pair لـأي عقد من العائلة**
- P3D / F3D / IND / SHORT / RP1 / BC2 — كلها ليست متاحة للتداول
- لا يمكن شراء tokens خارج الـbonding curve
- الـbonding curve يضمن أن أي شراء جديد يخفف الـsupply

### الخلاصة لـPoWH3D family
- **Dividends مودعة في الـcontract** (~4,000 ETH)
- **توزيعها يعتمد على holders حاليين** (نسبياً لـtoken count)
- **ما من DEX market** = صعب الوصول للـtokens
- **الـcontract حي تقنياً** لكن لا نشاط منذ 2019

**الاسترداد ممكن لـ:** holders الأصليين الذين يستدعون `withdraw()` على dividends المتراكمة.

---

## 🏪 الفئة 3: Old DEXs (EtherDelta-style — 5 عقود)

### العقود
1. **SingularX** - 857 ETH (`withdrawToken`, `withdraw(uint256)`)
2. **SwissCrypto** - 14.73 ETH (⚠️ **بـSELFDESTRUCT**)
3. **Coinchangex** - 17.35 ETH
4. **Decentrex** - 33.11 ETH
5. **Joyso DEX** - 85.34 ETH

### النمط الموحد
كلها تستخدم نمط **EtherDelta-style**:
```solidity
mapping(address => mapping(address => uint256)) public tokens;
function deposit() external payable { tokens[0][msg.sender] += msg.value; }
function withdraw(uint256 amount) external {
    require(tokens[0][msg.sender] >= amount);
    tokens[0][msg.sender] -= amount;
    msg.sender.transfer(amount);
}
```

### الاسترداد
**يحتاج**: المودِع الأصلي بمفتاحه الخاص يستدعي `withdraw(amount)`.

**SwissCrypto مع SELFDESTRUCT**: لو الـowner يستدعي `selfdestruct(beneficiary)`, الـ14 ETH تذهب للـbeneficiary (probably owner). لا فائدة لنا.

---

## 💎 الفئة 4: DeFi Protocols (5 عقود)

| العقد | الرصيد | Note |
|-------|--------|------|
| **MCDEX Perp** (DEX) | 559.71 ETH | perp dex، user-keyed positions |
| **KeeperDAO/Rook** | 413.13 ETH | flashbot keeper system |
| **Keep Network** | 234.42 ETH | tBTC staking |
| **Opyn Crab V2** | 106.08 ETH | options strategy vault |
| **Celer EthPool** | 70.26 ETH | bridge liquidity pool |
| **Unagii Vault** | 11.74 ETH | yield vault |
| **ETH Staking Rewards** | 59.67 ETH | staking |

### كلها user-keyed
- MCDEX: positions ربطت بـmsg.sender
- Keeper/Opyn/Unagii: shares معتمدة على depositor
- Celer: liquidity provider tokens

**الاسترداد ممكن لـ:** المستخدمين الأصليين بمفاتيحهم الخاصة.

---

## 🎯 خريطة الاسترداد الشاملة

| العقد | ETH | الاسترداد ممكن لـ |
|-------|-----|----------------|
| Old WETH (2016) | 1,514 | حاملي WETH balance (مجهولين) |
| PoWH3D (P3D) | 2,092 | حاملي P3D حاليين |
| Fomo3D Long | 1,117 | لاعبي F3D النشطين |
| GandhiJi | 663 | حاملي IND |
| MCDEX Perp | 560 | المتداولين |
| KeeperDAO | 413 | depositors |
| Keep Network | 234 | stakers |
| Opyn Crab V2 | 106 | strategy depositors |
| Joyso DEX | 85 | EtherDelta-style users |
| Fomo3D Quick | 84 | players |
| Fomo3D Short | 77 | players |
| Celer Bridge | 70 | LPs |
| ETH Staking | 60 | stakers |
| Decentrex | 33 | EtherDelta-style users |
| ReadyPlayerONE | 25 | players |
| Coinchangex | 17 | EtherDelta users |
| BitConnect2 | 15 | BC2 holders |
| SwissCrypto | 15 | EtherDelta users (selfdestruct exists) |
| Unagii Vault | 12 | depositors |
| SingularX | 858 | EtherDelta-style users |
| **المجموع** | **8,050** | **مفاتيح خاصة محددة** |

---

## ⚠️ الواقع المؤكد

**0 ETH قابلة للاسترداد بدون مفتاح خاص محدد.**

كل عقد من الـ20:
- إما user-keyed (مودعين أصليين)
- إما token-keyed (حاملي tokens خاصة بالعقد)
- إما owner-keyed (admin محدد)
- إما permanently locked

**النمط الإجباري:** msg.sender يجب أن يطابق طرف محدد لـwithdraw.

---

## 🔍 الفرص النظرية المُستبعدة

### Old WETH (1,514 ETH)
- **مستحيل بدون** WETH holder address + private key
- لا events = لا قائمة holders
- 10 سنوات من الجمود = الـholders شبه أكيد ضائعين

### PoWH3D Dividends (~2,092 ETH)
- **Cycle complete**: لا activity منذ 2019 = لا dividends جديدة
- Existing dividends مرتبطة بـcurrent holders فقط
- لا DEX = لا access للـtokens

### Fomo3D Long (1,117 ETH)
- لعبة keys-and-pots
- Pot هذا من round متوقفة قبل اكتمالها
- Winner = آخر مشتري عند انتهاء العداد
- لكن العداد توقف عن العمل فعلياً منذ 2019

---

## 📂 ملفات النتائج

| الملف | المحتوى |
|-------|---------|
| `analysis/forgotten_contracts_scan.json` | الفحص الكامل لـ20 عقد |
| `analysis/old_weth_holders.json` | محاولة enumerate WETH holders (فشلت) |
| `analysis/powh3d_holders.json` | محاولة enumerate P3D holders |
| `analysis/fomo3d_arbitrage_analysis.json` | تحليل اقتصاديات Fomo3D |

---

## 🧠 الأدوات المستخدمة

- `auto_scan.py` (من bug_bounty_kit) — فحص الـbytecode
- `analyze_contract.py` — deep dive
- `source_fetcher_v2.py` — Sourcify integration
- `bytecode_disasm.py` — opcode analysis
- Custom event scanners

كلها موجودة في `lost_eth_scanner/` و `bug_bounty_kit/` على GitHub.

---

## 🎯 الخلاصة النهائية

بعد فحص forensic شامل لـ20 عقد بـ8,050 ETH:

✅ **العقود حقيقية ومؤكدة** — كل الأرصدة محققة من RPC
✅ **معظم الـcontracts verified** — source code متاح للمراجعة
✅ **الـmechanisms واضحة** — كلها user/token/owner keyed
❌ **لا فرص استرداد لمفاتيح غير مالكة** — كل ETH تنتمي لأشخاص محددين
❌ **لا exploits معروفة** — العقود نظيفة من ثغرات بدائية

**الوحيدون اللي يقدرون يستردون:**
- مالكي addresses أودعت في DEXs (5 عقود)
- حاملي P3D/F3D/IND/BC2 tokens (Fomo3D family)
- depositors في DeFi vaults (Keeper, Opyn, Unagii, Celer)
- WETH holders في 0xECF8 (مجهولي الهوية)

**الفائدة الفعلية للأداة:** قاعدة بيانات للباحثين الأمنيين + فهم تاريخي للـDeFi 2018-2022.
