# Lost ETH Scanner

أداة لفحص العقود المنسية على Ethereum والبحث عن أرصدة عالقة قابلة للاسترداد.

## ⚖️ الاستخدام الأخلاقي

هذه الأداة تفحص الأرصدة **المسجلة باسم العنوان الذي تقدمه**. لاسترداد الأموال يجب أن تملك المفتاح الخاص لهذا العنوان. لا توجد طريقة لاستخراج أموال غيرك.

## 📋 ما تفحصه الأداة

12+ عقد منسية مشهورة:

| العقد | النوع | ملاحظة |
|-------|------|--------|
| IDEX 1.0 | DEX | ~16,168 ETH عالقة |
| EtherDelta v3 | DEX | الأشهر |
| EtherDelta v2 | DEX | إصدار أقدم |
| Token.Store | DEX | متروكة من الفريق |
| Saturn Network | DEX | فعّالة |
| DDEX | DEX | فعّالة |
| Bancor old | AMM | deprecated |
| AirSwap v1 | OTC | deprecated |
| 0x Protocol v1 | DEX | deprecated |
| Joyso | DEX | متروكة |
| Compound v1 | Lending | deprecated |
| MakerDAO SAI | CDP | deprecated |

## 🚀 الاستخدام

### 1. فحص عنوان واحد
```bash
python3 scanner.py 0xYourOldAddress
```

### 2. فحص عدة عناوين
```bash
python3 scanner.py 0xAddr1 0xAddr2 0xAddr3
```

### 3. توليد معاملة سحب
```bash
python3 withdraw_helper.py 0x2a0c0DBEcC7E4D658f48E01e3fA353F44050c208 0x0000000000000000000000000000000000000000 1000000000000000000
```

## 🔑 كيف تعرف عناوينك القديمة؟

ابحث في:
1. **MetaMask:** Settings → Advanced → "Show all accounts"
2. **MEW keystores:** ملفات `UTC--*` على جهازك
3. **إيميلات قديمة:** `IDEX`, `EtherDelta`, `deposit`
4. **Hardware wallets:** Ledger/Trezor → all derived addresses
5. **Browser history:** البحث عن "etherscan address"

## ⚠️ تحذيرات

- **لا تشارك مفتاحك الخاص أبداً** حتى مع هذه الأداة
- استخدم MetaMask أو hardware wallet لتوقيع المعاملة
- اختبر بمبلغ صغير أولاً إذا الرصيد كبير

## 🛠 إضافة عقود جديدة

عدّل ملف `contracts.json` لإضافة عقود إضافية.

## 📚 موارد

- [forgotteneth.com](https://forgotteneth.com/) - أداة ويب مشابهة
- [Lost-ETH GitHub](https://github.com/jconorgrogan/Lost-ETH) - قائمة شاملة
