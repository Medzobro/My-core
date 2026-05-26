# 🐛 13 نوع ثغرة في Smart Contracts (مع أمثلة عملية)

> دليل عملي لكل ثغرة شائعة + الكود الـvulnerable + الـexploit + الـfix.

---

## 1. 💉 Reentrancy

**التصنيف**: SWC-107 | **Severity**: Critical عادةً

### الكود الـvulnerable
```solidity
contract VulnerableBank {
    mapping(address => uint) public balances;
    
    function deposit() external payable {
        balances[msg.sender] += msg.value;
    }
    
    function withdraw() external {
        uint amount = balances[msg.sender];
        // ❌ external call BEFORE state change
        (bool ok,) = msg.sender.call{value: amount}("");
        require(ok);
        balances[msg.sender] = 0;
    }
}
```

### الـExploit
```solidity
contract Attacker {
    VulnerableBank target;
    
    function attack() external payable {
        target.deposit{value: 1 ether}();
        target.withdraw();
    }
    
    receive() external payable {
        if (address(target).balance >= 1 ether) {
            target.withdraw();  // re-enter
        }
    }
}
```

### الـFix (Checks-Effects-Interactions)
```solidity
function withdraw() external {
    uint amount = balances[msg.sender];
    balances[msg.sender] = 0;  // ✅ state change FIRST
    (bool ok,) = msg.sender.call{value: amount}("");
    require(ok);
}
```

أو استخدم `ReentrancyGuard` من OpenZeppelin.

**أمثلة تاريخية**: The DAO ($60M, 2016), Cream Finance ($130M, 2021)

---

## 2. 🔢 Integer Overflow / Underflow

**التصنيف**: SWC-101 | **Severity**: High

```solidity
// قبل Solidity 0.8.0 (لا overflow protection)
function transfer(address to, uint amount) external {
    require(balances[msg.sender] >= amount);
    balances[msg.sender] -= amount;  // قد يحدث underflow!
    balances[to] += amount;
}
```

**الـFix**: Solidity ≥0.8.0 محمي تلقائياً. أو استخدم `SafeMath`.

---

## 3. 🔓 Access Control Issues

```solidity
// ❌ كل واحد يقدر يعدل الـowner!
function setOwner(address newOwner) external {
    owner = newOwner;
}

// ✅
modifier onlyOwner() {
    require(msg.sender == owner, "Not owner");
    _;
}
function setOwner(address newOwner) external onlyOwner {
    owner = newOwner;
}
```

**أمثلة**: Parity Wallet $30M frozen (initWallet callable by anyone)

---

## 4. 🔮 Oracle Manipulation

```solidity
// ❌ vulnerable: spot price from a single DEX
function getPrice(address token) public view returns (uint) {
    return IUniswapV2Pair(pair).getReserves();
}

// ✅ TWAP من Uniswap V3 oracle
function getPrice(address token) public view returns (uint) {
    return OracleLibrary.consult(pool, secondsAgo);
}
```

**أمثلة**: Mango Markets ($117M, 2022), Cream Finance, bZx

---

## 5. ⚡ Flash Loan Attacks

```solidity
// تستخدم flash loan لـmanipulate price ثم تستفيد
function attack() external {
    aave.flashLoan(amount);
}

function executeOperation(...) external {
    swapOnDex(amount);  // dump price
    targetProtocol.exploit();  // benefit from low price
    swapBack();
    repay(amount);
}
```

**Defense**: TWAPs, multi-block locks, Chainlink oracles.

---

## 6. ✍️ Signature Replay

```solidity
// ❌ لا يستخدم nonce
function transfer(uint amount, bytes memory sig) external {
    bytes32 h = keccak256(abi.encodePacked(amount, msg.sender));
    address signer = recover(h, sig);
    require(signer == owner);
    payable(msg.sender).transfer(amount);
}

// ✅ مع nonce
mapping(address => uint) public nonces;
function transfer(uint amount, uint nonce, bytes memory sig) external {
    require(nonce == nonces[msg.sender]++);
    bytes32 h = keccak256(abi.encodePacked(amount, msg.sender, nonce, address(this), block.chainid));
    // ...
}
```

---

## 7. 🏃 Front-Running / MEV

```solidity
// ❌ user يشتري بسعر معين، MEV يسبقه
function swapExactETHForTokens(uint minOut) external payable;

// ✅ الـuser يحدد slippage بنفسه + deadline
function swapExactETHForTokens(uint minOut, uint deadline) external payable {
    require(block.timestamp <= deadline);
    // ...
}
```

---

## 8. 💀 Self-Destruct in Library

```solidity
// ❌ Parity Multisig 2017 - مشكلة!
library WalletLibrary {
    function kill() external {
        selfdestruct(msg.sender);
    }
}

// المستخدم العشوائي devops199 استدعاها
// → 514K ETH frozen forever في Parity wallets
```

---

## 9. 🎭 Storage Collision (Proxies)

```solidity
// Proxy storage slot 0 = implementation
// إذا الـ implementation contract يستخدم slot 0 لـowner
// = collision!

// ✅ EIP-1967 - يحدد slots صعبة
bytes32 constant IMPL_SLOT = 
    0x360894a13ba1a3210667c828492db98dca3e2076cc3735a920a3ca505d382bbc;
```

---

## 10. 🔄 Initialization Issues

```solidity
contract Vulnerable {
    address public admin;
    bool public initialized;
    
    // ❌ initialize callable by anyone if init is forgotten
    function initialize() external {
        admin = msg.sender;
        initialized = true;
    }
}
```

**Fix**: deploy + initialize in same tx, أو initializer modifier من OZ.

---

## 11. 🔢 Precision Loss / Rounding

```solidity
// ❌ تقسيم قبل الضرب
fee = amount / 1000 * 5;  // إذا amount < 1000، fee = 0!

// ✅ ضرب قبل التقسيم
fee = amount * 5 / 1000;
```

---

## 12. 🎲 Bad Randomness

```solidity
// ❌ يمكن للـminer التلاعب
uint random = uint(keccak256(abi.encodePacked(block.timestamp, block.difficulty)));

// ✅ Chainlink VRF
function fulfillRandomWords(uint requestId, uint[] memory randomWords) internal {
    // use chainlink-provided randomness
}
```

---

## 13. 🚪 tx.origin Authorization

```solidity
// ❌
modifier onlyOwner() {
    require(tx.origin == owner);
    _;
}
// إذا الـowner استخدم phishing contract، أي تنفيذ يدخل onlyOwner!

// ✅
require(msg.sender == owner);
```

---

## 🎯 Priority للـBug Hunting

ركز على هذه الفئات (الأعلى احتمالاً للوجود):

1. **Logic Errors** في math/pricing - أصعب الكشف، أعلى مكافأة
2. **Reentrancy** - دائماً يوجد في contracts قديمة
3. **Access Control** - مفقودة في initialization functions
4. **Oracle Manipulation** - في DeFi protocols تستخدم spot prices
5. **Storage Collision** - في proxies وupgrades

---

## 📚 موارد مفيدة

- **SWC Registry**: swcregistry.io
- **Solidity by Example**: solidity-by-example.org/hacks
- **Smart Contract Hacks**: github.com/SunWeb3Sec/DeFiHackLabs
- **Damn Vulnerable DeFi**: damnvulnerabledefi.xyz
- **Trail of Bits**: github.com/crytic/building-secure-contracts
