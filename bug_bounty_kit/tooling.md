# 🛠 الأدوات الأساسية للـSmart Contract Auditor

> الـtoolkit الكامل + التثبيت + أمثلة استخدام.

---

## 1. ⚒️ Foundry (الأهم!)

أقوى framework لتطوير + اختبار + fuzz testing الـsmart contracts.

### التثبيت
```bash
curl -L https://foundry.paradigm.xyz | bash
foundryup
```

### الأدوات داخله
- **forge**: Build, test, fuzz
- **cast**: تفاعل مع mainnet
- **anvil**: local fork (محلي = سريع جداً)

### Fork mainnet للاختبار
```bash
anvil --fork-url https://ethereum-rpc.publicnode.com

# في terminal آخر:
cast call 0xb47e3cd8... "name()" --rpc-url http://localhost:8545
```

### مثال exploit test
```solidity
// test/Exploit.t.sol
import "forge-std/Test.sol";

contract ExploitTest is Test {
    function setUp() public {
        // fork mainnet at specific block
        vm.createSelectFork("mainnet", 18000000);
    }
    
    function testExploit() public {
        // your exploit code here
        // vm.prank(attacker) - simulate any address
        // vm.deal(attacker, 100 ether) - give them ETH
    }
}

// Run:
// forge test --match-test testExploit -vvvv
```

---

## 2. 🐍 Slither (static analysis)

اكتشاف ثغرات شائعة بدون تشغيل الكود.

### التثبيت
```bash
pip3 install slither-analyzer
```

### الاستخدام
```bash
# تحليل عقد
slither contracts/MyContract.sol

# تحليل مشروع كامل
slither .

# تحليل عنوان mainnet مباشرة (يحتاج Etherscan API key)
slither 0xbCF935D206Ca32929e1b887a07Ed240f0D8CCD22 \
    --etherscan-apikey YOUR_KEY

# Print human-readable summary
slither --print human-summary .

# Print contract calls
slither --print call-graph .

# Print data dependency
slither --print data-dependency .
```

### Detectors المهمة
```bash
# يكشف 80+ نوع ثغرة:
slither . --detect reentrancy-eth,reentrancy-no-eth,uninitialized-state
slither . --detect arbitrary-send,suicidal,erc20-interface
```

---

## 3. 🔍 Mythril (symbolic execution)

أداة symbolic execution أعمق من Slither.

```bash
pip3 install mythril
myth analyze contracts/Vulnerable.sol
```

---

## 4. 🦔 Echidna (fuzzing)

Property-based fuzz testing.

```bash
# install via Docker
docker pull trailofbits/eth-security-toolbox

# أو brew
brew install echidna
```

```solidity
// echidna_test.sol
contract Test {
    uint balance = 0;
    
    function deposit(uint amount) public {
        balance += amount;
    }
    
    // Echidna test
    function echidna_balance_never_negative() public returns (bool) {
        return balance >= 0;
    }
}

// Run: echidna echidna_test.sol
```

---

## 5. 🔬 Tenderly Debugger

Online tool for transaction debugging.

- **URL**: tenderly.co
- **Free tier**: 50 simulations/month
- **استخدام**:
  - افتح أي tx hash
  - Step-through execution
  - رؤية stack/storage/memory في كل خطوة

---

## 6. 📊 Etherscan Read/Write Contract

أبسط أداة للتفاعل المباشر مع contracts:

- **Read**: قراءة state بدون tx
- **Write**: إرسال tx (يحتاج wallet)
- **Verified Source**: تشف الـsource code

---

## 7. 🛠 Foundry Cheatcodes (Essential)

```solidity
// fork mainnet at specific block
vm.createSelectFork("mainnet", 18500000);

// simulate any caller
vm.prank(0xWhale);
victim.transfer(amount);

// simulate any state
vm.deal(attacker, 100 ether);
vm.store(target, slot, value);

// time travel
vm.warp(block.timestamp + 1 days);
vm.roll(block.number + 100);

// expect specific revert
vm.expectRevert("Not authorized");

// emit specific event
vm.expectEmit(true, true, true, true);
emit Transfer(alice, bob, 100);
```

---

## 8. 🔧 أدوات إضافية مفيدة

### EVM Bytecode Tools
- **Panoramix**: decompile bytecode → readable code
- **bytegraph**: visualize control flow

### Static Analyzers
- **Securify**: ChainSecurity من ETH Zurich
- **Olympix**: AI-assisted analysis
- **Wake** by Ackee: integrated VS Code

### Sourcify integration (already في our scanner)
```python
# Get verified source
import urllib.request, json
url = f'https://sourcify.dev/server/files/any/1/{address}'
data = json.loads(urllib.request.urlopen(url).read())
```

---

## 9. 🧰 Workflow الأمثل

```
1. اختر هدف (e.g. specific Immunefi program)
2. forge clone + read README
3. slither . → fix easy findings
4. أكتب tests + fuzz tests
5. forge test --fuzz-runs 100000
6. mythril على الـcritical contracts
7. manual review للـlogic
8. write PoC + report
9. submit عبر Immunefi
```

---

## 10. 📁 مشروع starter

```bash
# أنشئ مشروع foundry جديد
forge init my-bug-hunt
cd my-bug-hunt

# أضف dependencies
forge install OpenZeppelin/openzeppelin-contracts

# أضف الـtarget للاختبار
mkdir test-targets/
# clone repo target...

# اكتب test:
# tests/MyExploit.t.sol

# شغّل:
forge test -vvv
forge coverage
```
