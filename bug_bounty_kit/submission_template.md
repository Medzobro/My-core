# 📝 قالب التقرير المهني (Submission Template)

> الفرق بين تقرير يُقبل ومرفوض = وضوح + reproducibility + impact analysis.

---

## 🎯 صيغة Immunefi Standard

```markdown
# [TITLE: Critical/High/Medium/Low — Brief Description]

## Severity
**Critical** / **High** / **Medium** / **Low** / **Informational**

## Vulnerability Type
- [ ] Reentrancy
- [ ] Access Control
- [ ] Logic Error
- [ ] Oracle Manipulation
- [ ] Other: ___

## Target
- **Contract**: 0xContractAddress
- **Function**: functionName(args)
- **Network**: Ethereum / Arbitrum / etc.

## Description
وصف مختصر للثغرة - ماذا يحدث وكيف.

## Impact
ماذا يستطيع المهاجم أن يفعل؟
- المبلغ at risk: $X
- المستخدمين المتضررين: X
- نوع الضرر: loss/freeze/manipulation

## Steps to Reproduce
1. الخطوة الأولى
2. الخطوة الثانية
3. ...

## Proof of Concept (Code)
```solidity
// PoC.sol
contract Exploit {
    function attack() external {
        // الكود الكامل القابل للتنفيذ
    }
}
```

## How to Run
```bash
forge test --match-test testExploit -vvvv --fork-url $RPC --fork-block-number 18500000
```

## Mitigation
الـfix المقترح:
```solidity
// قبل
function vulnerable() ...

// بعد
function fixed() ...
```

## References
- SWC: SWC-XXX
- Similar hack: [name]($amount)
- OpenZeppelin docs: link
```

---

## ✅ تقرير ممتاز (Example)

```markdown
# [Critical] Reentrancy in withdraw() allows full drain

## Severity: Critical

## Target
- Contract: 0x... at line 145 of Vault.sol
- Function: `withdraw(uint amount)`

## Description
The `withdraw` function transfers ETH to msg.sender BEFORE updating
the user's balance. This allows a malicious contract to recursively
call back into withdraw and drain the entire vault.

## Impact
- Funds at risk: 12,000 ETH (~$30M)
- Affected users: All depositors
- Severity: Total loss of contract balance

## Steps to Reproduce
1. Attacker contract deposits 1 ETH via deposit()
2. Attacker calls withdraw()
3. In receive() callback, attacker calls withdraw() again
4. Loop until contract empty

## Proof of Concept

[full code]

## Run with Foundry
```bash
forge test --match-test testReentrancy --fork-url $MAINNET_RPC -vvv
```

Expected output: Attacker drains 12,000 ETH from vault

## Mitigation

Use ReentrancyGuard from OpenZeppelin OR follow CEI pattern:
```solidity
function withdraw(uint amount) external {
    require(balances[msg.sender] >= amount);
    balances[msg.sender] -= amount;  // ✅ state FIRST
    (bool ok,) = msg.sender.call{value: amount}("");
    require(ok);
}
```

## References
- SWC-107: https://swcregistry.io/docs/SWC-107
- The DAO hack ($60M)
- Cream Finance ($130M)
```

---

## ❌ تقرير سيء (Example)

```
عنوان: bug

في contract X في function Y فيه مشكلة. 
المهاجم يقدر يأخذ الفلوس.
أرجو الإصلاح.
```

**لماذا سيء**:
- لا تفاصيل
- لا PoC
- لا impact analysis
- لا mitigation
- → سيُرفض

---

## 💡 نصائح مهمة

### 1. اكتب PoC قابل للتنفيذ
لا تكتب فقط نظري — قدم كود forge test كامل.

### 2. حدد الـimpact بدقة
- ليس "خسارة محتملة" بل "$30M at risk"
- اربطه بـrelevant data (TVL, balance, users)

### 3. صنّف severity حسب Immunefi
- **Critical**: ≥10% TVL or full drain or unauth governance
- **High**: <10% TVL drain, theft via tricks
- **Medium**: temporary lock, griefing
- **Low**: minor inconvenience

### 4. اكتب بالإنجليزية
كل المنصات الكبرى تستقبل بالإنجليزية فقط.

### 5. لا تنشر علناً قبل الإفصاح
- Submission window: 24-48 hours response
- Disclosure: عادة بعد الـpatch deployed
- لا Twitter/Discord قبل ذلك

### 6. كن واقعي مع الـseverity
- منصات الـbug bounty لديها triagers خبراء
- السقوط من Critical → Medium يقلل المكافأة كثيراً
- الإفراط في الـseverity = فقدان الـreputation

---

## 🏆 أمثلة لتقارير ناجحة

- **Yearn Finance bug** (2021): Samczsun، $50K, 5-line bug
- **Aurora Security** (2022): $6M payout, $200M at risk
- **Sushiswap RouteProcessor** (2023): $400K
- **Wormhole** (2022): $10M payout

كلها كانت تقارير clean + reproducible + clear impact.
