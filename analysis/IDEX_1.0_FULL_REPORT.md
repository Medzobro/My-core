# 🔬 التقرير الكامل: IDEX 1.0 Exchange Contract
## `0x2a0c0DBEcC7E4D658f48E01e3fA353F44050c208`

---

## 🎯 الهوية النهائية

| الحقل | القيمة |
|------|--------|
| **اسم البروتوكول** | IDEX 1.0 (سابقاً Aurora DEX) |
| **اسم العقد التقني** | `Exchange` |
| **الشركة المطورة** | Aurora Labs S.A. |
| **المؤسسون** | Alex Wearn, Phil Wearn |
| **تاريخ النشر** | 27 سبتمبر 2017 - 20:43:49 UTC |
| **Compiler** | Solidity 0.4.16 |
| **مفتوح المصدر** | ✅ متحقق منه على Sourcify |
| **النوع المعماري** | Hybrid DEX (off-chain order book + on-chain settlement) |
| **مشتق من** | EtherDelta (مع تعديلات جوهرية) |

---

## 📊 الإحصائيات الكلية (حتى اليوم 22 مايو 2026)

| المؤشر | القيمة |
|-------|--------|
| **إجمالي المعاملات** | 9,792,220 |
| **Token transfers** | 1,924,223 |
| **إجمالي الـ gas المستهلك** | 1,084,451,387,663 gwei |
| **عمر العقد** | 8 سنوات و 8 أشهر |
| **الحالة الحالية** | 🟢 نشط (آخر سحب اليوم!) |

---

## 💰 الأموال العالقة بالعقد - تفصيل دقيق

### الإجمالي التقريبي: **~$479 مليون دولار** 🤯

| الفئة | الكمية | القيمة بالـ USD |
|------|--------|----------------|
| **ETH** | 16,168.16 | ~$34,400,000 |
| **1,050+ توكن ERC-20** | متنوع | ~$445,300,000 |
| **882+ توكن آخر** (NFT/غير مسعّر) | غير محدد | غير معروف |

### 🏆 أكبر 15 توكن عالق (بقيمة USD):

```
$ 419,208,010   FTT   FarmaTrust Token         10,818,271 token
$  10,177,656   QNT   Quant                       131,681 token
$   4,522,417   SOL   Sola Token                   52,862 token
$   2,443,160   SPRK  Sparkster                 3,242,859 token
$   1,435,430   TRAC  OriginTrail               3,236,018 token
$   1,244,693   NEXO  NEXO                      1,438,749 token
$   1,115,256   C8    Carboneum                   969,787 token
$     350,307   XYO   XYO Network              74,279,769 token
$     315,756   XCD   CapdaxToken              51,002,763 token
$     307,014   IDXM  IDEX Membership                 214 token  ⭐ توكن العضوية الخاص ببورصة IDEX
$     272,050   NOW   ChangeNOW                   599,232 token
$     209,703   HOT   Holo                    521,039,083 token
$     207,952   SPU+  Spurt Plus                  396,721 token
$     198,147   FXC   Flexacoin                32,235,412 token
$     196,482   TEL   Telcoin                  63,242,023 token
```

> ⚠️ **ملاحظة:** القيمة الحقيقية القابلة للتحويل أقل بكثير. الـ FTT بـ $419M مثلاً سعره الاسمي مرتفع لكن السيولة الفعلية شبه معدومة. **القيمة الحقيقية القابلة للسحب ربما $50-80M**.

---

## 🏗 المعمارية والـ Storage Layout

### تخطيط التخزين (Storage Slots)

```solidity
// slot 0:  address public owner                    = 0x6b770f1a6bff9151f437f2eab907fff132dd86a5
// slot 1:  mapping(address => uint256) invalidOrder
// slot 2:  mapping(address => mapping(address => uint256)) tokens  // ⭐ المفتاح الذهبي
// slot 3:  mapping(address => bool) admins
// slot 4:  mapping(address => uint256) lastActiveTransaction
// slot 5:  mapping(bytes32 => uint256) orderFills
// slot 6:  address public feeAccount                = 0x034767f3c519f361c5ecf46ebfc08981c629d381
// slot 7:  uint256 public inactivityReleasePeriod  = 240 (~1 ساعة على ETH)
// slot 8:  mapping(bytes32 => bool) traded
// slot 9:  mapping(bytes32 => bool) withdrawn
```

### كيفية حساب رصيد المستخدم في الـ storage

```python
# لمعرفة رصيد user من token:
# slot = keccak256(user . keccak256(token . 2))
import sha3
def user_balance_slot(token, user):
    inner = sha3.keccak_256(bytes.fromhex(token[2:].rjust(64,'0')) + (2).to_bytes(32,'big')).digest()
    outer = sha3.keccak_256(bytes.fromhex(user[2:].rjust(64,'0')) + inner).digest()
    return '0x' + outer.hex()
```

---

## ⚙️ كل دوال العقد - 32 دالة بالتفصيل

### 🔓 دوال عامة (يستدعيها أي مستخدم)

#### 1. `deposit() payable` - `0xd0e30db0`
```solidity
function deposit() payable {
    tokens[address(0)][msg.sender] += msg.value;  // ETH = address(0)
    lastActiveTransaction[msg.sender] = block.number;
    Deposit(address(0), msg.sender, msg.value, tokens[address(0)][msg.sender]);
}
```
**الوظيفة:** إيداع ETH في حسابك داخل البورصة.

#### 2. `depositToken(address token, uint256 amount)` - `0x338b5dea`
```solidity
function depositToken(address token, uint256 amount) {
    tokens[token][msg.sender] += amount;
    lastActiveTransaction[msg.sender] = block.number;
    Token(token).transferFrom(msg.sender, this, amount);
}
```
**الوظيفة:** إيداع توكن ERC-20. يحتاج `approve` مسبقاً.

#### 3. **`withdraw(address token, uint256 amount)`** - `0xf3fef3a3` ⭐ الدالة المهمة
```solidity
function withdraw(address token, uint256 amount) returns (bool) {
    if (block.number - lastActiveTransaction[msg.sender] < inactivityReleasePeriod) throw;  // ⚠️ مهم
    if (tokens[token][msg.sender] < amount) throw;
    tokens[token][msg.sender] -= amount;
    if (token == address(0)) msg.sender.send(amount);
    else Token(token).transfer(msg.sender, amount);
}
```
**الوظيفة:** سحب رصيدك. هذي الدالة اللي يستخدمها 1,341 من أصل 1,500 معاملة حديثة على العقد!

**الشروط الحاسمة:**
- ✅ يمر `inactivityReleasePeriod` = 240 block (~1 ساعة) من آخر معاملة لك
- ✅ رصيدك في `tokens[token][msg.sender]` ≥ المبلغ المطلوب
- ❌ لا أحد يقدر يسحب نيابة عنك (لازم `msg.sender == you`)

#### 4. `balanceOf(address token, address user) view` - `0xf7888aec`
```solidity
return tokens[token][user];
```
**الوظيفة:** عرض رصيد user من token. هذي الطريقة الرسمية لفحص رصيدك.

#### 5. `tokens(address, address) view` - `0x508493bc`
**الوظيفة:** نفس `balanceOf` لكن وصول مباشر للـ mapping.

---

### 🔐 دوال admin/owner فقط

#### 6. `setOwner(address newOwner)` - `0x13af4035` (`onlyOwner`)
**الوظيفة:** نقل ملكية العقد لعنوان آخر.

#### 7. `setAdmin(address admin, bool isAdmin)` - `0x4b0bddd2` (`onlyOwner`)
**الوظيفة:** تعيين أو إزالة admin (لتنفيذ trades).

#### 8. `setInactivityReleasePeriod(uint256)` - `0xdd93c74a` (`onlyAdmin`)
**الوظيفة:** تعديل فترة الـ cooldown (max = 1,000,000 block ≈ 5 شهور).
> 📌 **اكتُشف:** الـ owner استدعى هذي الدالة آخر مرة في **16 أكتوبر 2020**. آخر نشاط فعلي للمالك.

#### 9. `adminWithdraw(...)` - `0x2295115b` (`onlyAdmin`)
```solidity
function adminWithdraw(address token, uint256 amount, address user, uint256 nonce, 
                       uint8 v, bytes32 r, bytes32 s, uint256 feeWithdrawal) returns (bool)
```
**الوظيفة:** السماح للـ admin بتنفيذ سحب نيابة عن user **بشرط توقيع المستخدم نفسه**.

⚠️ **أمان حرج:** الـ admin **لا يستطيع** سحب أموال user بدون توقيعه. الـ `ecrecover` يتحقق من التوقيع. هذي ضمانة أمان حقيقية في الكود.

#### 10. `trade(uint256[8], address[4], uint8[2], bytes32[4])` - `0xef343588` (`onlyAdmin`)
**الوظيفة:** تنفيذ trade بين maker و taker بناءً على توقيعَيهم. الـ admin بس ينفذ، ما يقدر يحدد شروط.

#### 11. `invalidateOrdersBefore(address user, uint256 nonce)` - `0xb12de559` (`onlyAdmin`)
**الوظيفة:** إلغاء كل أوامر user بـ nonce أقل من المحدد.

---

### 📖 دوال للقراءة فقط (View)

| Selector | Function | الوظيفة |
|----------|----------|--------|
| `0x8da5cb5b` | `owner()` | عنوان المالك |
| `0x893d20e8` | `getOwner()` | نفس الشي |
| `0x65e17c9d` | `feeAccount()` | حساب الرسوم |
| `0xf31174ee` | `inactivityReleasePeriod()` | فترة الـ cooldown |
| `0x429b62e5` | `admins(address)` | هل العنوان admin؟ |
| `0x254dcfe2` | `lastActiveTransaction(address)` | آخر block فيه نشاط لك |
| `0xf7213db6` | `orderFills(bytes32)` | كم مل امتلأ من الأمر |
| `0xd5813323` | `traded(bytes32)` | هل تم تنفيذ هذا التريد |
| `0x3823d66c` | `withdrawn(bytes32)` | هل تم تنفيذ هذا الـ adminWithdraw |
| `0x83dbb27b` | `invalidOrder(address)` | minimum nonce المقبول |

---

### 🛠 دوال داخلية (helpers)

```solidity
function safeMul(uint a, uint b) returns (uint)  // 0xd05c78da
function safeSub(uint a, uint b) returns (uint)  // 0xa293d1e8
function safeAdd(uint a, uint b) returns (uint)  // 0xe6cb9013
function assert(bool) // 0x0674763c (مشهور بسبب Solidity 0.4.x)
```

---

## 🎭 الأشخاص والعناوين الرئيسية

### 👤 المالك الحالي (Owner)
```
0x6b770f1a6bff9151f437f2eab907fff132dd86a5
```
- **النوع:** EOA (Externally Owned Account)
- **الرصيد:** 0.0068 ETH (شبه فارغ)
- **آخر نشاط:** 16 أكتوبر 2020 (`setInactivityReleasePeriod`)
- **التفسير:** غالباً wallet إداري لفريق Aurora Labs/IDEX، تركوه كما هو لأن العقد ما عاد يحتاج إدارة (التداول توقف من زمان، فقط السحوبات تستمر)

### 🏗 منشئ العقد (Deployer)
```
0x33daedabab9085bd1a94460a652e7ffff592dfe3
```
- **النوع:** EOA نشط جداً (806+ معاملة)
- **آخر نشاط:** قريب جداً
- **يتعامل مع:** Uniswap (`addLiquidity`, `removeLiquidity`), `approve`, `transfer`, `multicall`
- **التفسير:** wallet خاص بمطور أو مؤسس Aurora Labs - لازال نشط

### 💵 حساب الرسوم (Fee Account)
```
0x034767f3c519f361c5ecf46ebfc08981c629d381
```
- **الرصيد:** 0.005 ETH تقريباً
- **التفسير:** الحساب اللي تتراكم فيه رسوم البورصة (0.1-10% حسب الـ trade)

### 🪙 توكنات IDEX/AURA المرتبطة
- `0xb705268213d593b8fd88d3fdeff93aff5cbdcfae` = **IDEX Token**
- `0xcdcfc0f66c522fd086a1b725ea3c0eeb9f9e8814` = **AURA Token**

---

## 🔒 التحليل الأمني

### ✅ نقاط قوة الكود
1. **لا توجد دالة withdrawAll** - الـ owner ما يقدر يخرب الكل
2. **`adminWithdraw` يتطلب توقيع user** عبر `ecrecover` - حماية ضد الـ rogue admin
3. **`inactivityReleasePeriod`** - يمنع front-running عند انعكاس trade
4. **`safeAdd/safeSub/safeMul`** - حماية من overflow (مهم في 0.4.x قبل ما تكون default)
5. **`fallback() throw`** - أي ETH يتم إرسالها بدون استدعاء `deposit()` تُرجع تلقائياً

### ⚠️ نقاط ضعف معروفة (في حدود الكود الحالي)
1. **يستخدم `throw`** بدلاً من `revert()` - من Solidity 0.4.x القديمة. يستهلك كل الـ gas (مشكلة UX بس).
2. **لا يرجع `bool` صريحاً في `withdraw()` على نجاح** - bug صغير في return.
3. **`Token` interface مبسط** - بعض الدوال الحديثة مفقودة، لكن متوافق مع ERC-20 الكلاسيكي.
4. **`setInactivityReleasePeriod` max 1,000,000 block** - حماية من قفل دائم.

### 🛡 لا يوجد فيه (المهم!)
- ❌ **لا يوجد `selfdestruct`** - رغم أن opcode `0xff` موجود في الكود لكنه ليس في مسار قابل للتنفيذ من قبل المالك
- ❌ **لا يوجد `delegatecall`** قابل للاستغلال (موجود في الـ bytecode لكن للـ token interface فقط)
- ❌ **لا يوجد دالة rescue/recover للمالك** - الفلوس داخل المستخدم خاصة بالمستخدم وحده

---

## 📈 أنماط النشاط الحالية (آخر 1500 معاملة)

```
withdraw                 1341 معاملة  (89.4%)  ← الناس لازالوا يستردون فلوسهم
depositToken               49 معاملة  (3.3%)   ← إيداعات نادرة (خطأ غالباً)
0x68747470 (= "http")      42 معاملة  (2.8%)   ← phishing junk، تنعكس
deposit                    29 معاملة  (1.9%)
kill                       10 معاملة  (0.7%)   ← محاولات سرقة فاشلة
destroy                     1 معاملة          ← محاولة سرقة فاشلة
```

> 🎭 **ملاحظة طريفة:** الـ 42 معاملة بـ `0x68747470` = "http" بالـ ASCII! يعني ناس راحت تبعث للعقد "https://..." كـ raw call data، ربما مخترقين فاشلين أو bots خربانة.

---

## 🆔 لمحة تاريخية - قصة IDEX

**2017:** Aurora Labs تطلق Aurora Token (AURA) و IDEX 1.0 كـ **أول بورصة لامركزية ذات تداول لحظي**.

**2018:** IDEX يصبح أكبر DEX على Ethereum من حيث الحجم لفترة طويلة. تصل لمليارات الدولارات في الحجم الشهري.

**2018-2019:** يبدأ IDEX بتقييد المستخدمين الأمريكيين (لأسباب SEC).

**2019:** اندماج AURA → IDEX rebranding.

**2020:** **إطلاق IDEX 2.0** - معماري جديد كامل، مبني على Polkadot/Substrate ثم Polygon. **الـ Exchange contract القديم (هذا) يتجمد عملياً للتداول**، ويبقى مفتوحاً فقط للـ withdrawals.

**2020 - الآن:** المستخدمين القدامى يكتشفون إن لديهم رصيد عالق ويسحبون. **آخر سحب: قبل ساعات قليلة (22 مايو 2026)**.

**اليوم:** العقد كحالة تذكارية - شاهد على عصر ICO mania و الـ DEX الأولى على Ethereum.

---

## 🚪 كيفية السحب (إذا كنت أحد المستخدمين القدامى)

### الشروط الإلزامية
1. ✅ تملك المفتاح الخاص لعنوان `X` كان قد أودع في IDEX قبل 2020
2. ✅ رصيدك في `tokens[token][X] > 0`
3. ✅ مر أكثر من 240 block (~1 ساعة) منذ آخر معاملة لـ `X` على العقد

### الكود الكامل للسحب

```python
# -*- coding: utf-8 -*-
"""
IDEX 1.0 Withdrawal Script
Use with caution. Test on testnet first if possible.
"""
from web3 import Web3

CONTRACT = '0x2a0c0DBEcC7E4D658f48E01e3fA353F44050c208'
RPC = 'https://eth.llamarpc.com'  # أو infura/alchemy/إلخ
w3 = Web3(Web3.HTTPProvider(RPC))

# عنوانك (اللي أودعت منه قديماً)
MY_ADDRESS = '0xYOUR_ADDRESS'  # غيّره
PRIVATE_KEY = 'YOUR_PRIVATE_KEY'  # ⚠️ لا تشاركها أبداً، استخدم env variable

# توكن: ETH = 0x0...0
TOKEN = '0x0000000000000000000000000000000000000000'  # ETH

# ABI مختصر
ABI = [
    {"name":"balanceOf","type":"function","stateMutability":"view",
     "inputs":[{"name":"token","type":"address"},{"name":"user","type":"address"}],
     "outputs":[{"type":"uint256"}]},
    {"name":"withdraw","type":"function","stateMutability":"nonpayable",
     "inputs":[{"name":"token","type":"address"},{"name":"amount","type":"uint256"}],
     "outputs":[{"type":"bool"}]},
    {"name":"lastActiveTransaction","type":"function","stateMutability":"view",
     "inputs":[{"name":"","type":"address"}],"outputs":[{"type":"uint256"}]},
    {"name":"inactivityReleasePeriod","type":"function","stateMutability":"view",
     "inputs":[],"outputs":[{"type":"uint256"}]},
]

c = w3.eth.contract(address=CONTRACT, abi=ABI)

# 1. فحص رصيدك
balance = c.functions.balanceOf(TOKEN, MY_ADDRESS).call()
print(f'رصيدك: {w3.from_wei(balance, "ether")} ETH')

if balance == 0:
    print('لا يوجد رصيد، توقف.')
    exit()

# 2. فحص الـ cooldown
last = c.functions.lastActiveTransaction(MY_ADDRESS).call()
period = c.functions.inactivityReleasePeriod().call()
current = w3.eth.block_number
ready_at = last + period
if current < ready_at:
    print(f'لازم تنتظر حتى block {ready_at} (الآن {current})')
    exit()

# 3. بناء معاملة السحب
tx = c.functions.withdraw(TOKEN, balance).build_transaction({
    'from': MY_ADDRESS,
    'nonce': w3.eth.get_transaction_count(MY_ADDRESS),
    'gas': 100000,
    'gasPrice': w3.eth.gas_price,
})

# 4. توقيع وإرسال
signed = w3.eth.account.sign_transaction(tx, PRIVATE_KEY)
tx_hash = w3.eth.send_raw_transaction(signed.rawTransaction)
print(f'tx: {tx_hash.hex()}')
```

### بدائل أسهل (بدون كود)
1. **MyEtherWallet (MEW):** اذهب لقسم Contracts → Interact → ألصق العنوان والـ ABI → استخدم `withdraw`
2. **Etherscan Write Contract:** [الرابط المباشر](https://etherscan.io/address/0x2a0c0dbecc7e4d658f48e01e3fa353f44050c208#writeContract) → Connect Wallet → استدعي `withdraw`
3. **Frame / MetaMask + Hardhat console:** نفس الطريقة لكن لمحبي الـ CLI

---

## 🚨 تحذيرات قبل أي تحرك

| ⚠️ | الخطر | التفصيل |
|---|------|---------|
| 🔴 | "خدمات استرداد" | لا أحد بإمكانه استرداد فلوس عنوان لا يملك مفتاحه. أي خدمة تطلب fees مقدماً = نصب |
| 🔴 | المفاتيح الخاصة | لا تدخلها في أي موقع، حتى MEW استخدمه offline |
| 🟡 | Gas | تكلفة `withdraw` ~50,000 gas، حساب رخيص نسبياً |
| 🟡 | inactivityReleasePeriod | بعد كل deposit أو trade لازم تنتظر 1 ساعة قبل ما تسحب |
| 🟢 | لا حدود زمنية | الفلوس ما تنتهي صلاحيتها، تظل عالقة للأبد لحين سحبها |

---

## 📚 مراجع وروابط

- [Etherscan: العقد](https://etherscan.io/address/0x2a0c0dbecc7e4d658f48e01e3fa353f44050c208)
- [Sourcify: الكود الموثق](https://sourcify.dev/#/lookup/0x2a0c0dbecc7e4d658f48e01e3fa353f44050c208)
- [IDEX Whitepaper (2018)](https://www.scribd.com/document/444279125/IDEX-Whitepaper-V0-7-6)
- [Globe Newswire: إطلاق IDEX](https://www.globenewswire.com/en/news-release/2018/01/22/1298553/0/en/First-Real-Time-Decentralized-Exchange-IDEX-Raises-6M-and-Announces-Strategic-Engagement-with-WINGS-Foundation.html)
- [EtherDelta source](https://github.com/etherdelta/smart_contract/blob/master/etherdelta.sol) (الأصل اللي اشتق منه IDEX)

---

## 🎯 خلاصة شاملة في 5 نقاط

1. **العقد = IDEX 1.0**، أول بورصة لامركزية حقيقية على Ethereum، من Aurora Labs.
2. **الفلوس داخله = ودائع المستخدمين**. مالك العقد لا يقدر يأخذها (مؤكد بالكود).
3. **~$479M اسمياً، ~$50-80M حقيقي قابل للتحويل**. أكبرها FTT لكن قيمته ضعيفة سيولة.
4. **العقد لازال يعمل للسحوبات فقط** منذ 2020 لما إطلاق IDEX 2.0. لا تداول جديد.
5. **السحب ممكن فقط لمن يملك المفتاح الخاص** لعنوان أودع في الماضي. لا توجد طريقة أخرى - لا hack ولا استرداد ولا "إذن من الخارج".
