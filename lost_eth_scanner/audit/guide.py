"""Recovery instructions for the contracts the audit can detect.

Each entry is a list of bilingual steps. The text is deliberately operational:
where to click, which function to call, which parameter goes where. Anything we
cannot verify gets an explicit warning instead of a confident guess.
"""

from __future__ import annotations

ETHERSCAN = "https://etherscan.io/address/{address}#writeContract"
ETHERSCAN_TOKEN = "https://etherscan.io/token/{address}#writeContract"
ZERO = "0x0000000000000000000000000000000000000000"

# Keyed by lower-case contract address.
STEPS: dict[str, dict] = {
    "0x23ea10cc1e6ebdb499d24e45369a35f43627062f": {
        "title_ar": "DigixDAO — استرداد DGD مقابل ETH",
        "difficulty": "medium",
        "steps": [
            (
                "عقد Acid أُنشئ بعد حل DigixDAO (Ragnarok 2020): يحرق توكنات DGD ويعيد ETH بسعر ثابت محفوظ في العقد.",
                "The Acid contract was deployed after DigixDAO's Ragnarok dissolution (2020): it burns DGD and returns ETH at a fixed on-chain rate.",
            ),
            (
                "أولاً approve على عقد DGD (0xe0b7927c…0e2a): نفّذ approve(0x23Ea10CC…062f, كامل رصيدك).",
                "First approve on the DGD token (0xe0b7927c…0e2a): call approve(0x23Ea10CC…062f, your full balance).",
            ),
            (
                "ثم على عقد Acid نفّذ burn() بلا وسائط — يحرق كل DGD ويرسل ETH إلى محفظتك فوراً.",
                "Then on Acid call burn() with no arguments — it burns all your DGD and sends the ETH to your wallet immediately.",
            ),
            (
                "السعر يُقرأ من weiPerNanoDGD() على العقد نفسه؛ لا تعتمد على سعر من موقع خارجي.",
                "The rate is read from weiPerNanoDGD() on the contract itself; do not trust an off-chain quote.",
            ),
        ],
        "note_ar": "لا يوجد استرداد جزئي: burn() يحرق كامل رصيد DGD في المحفظة. تحقق من الرقم قبل التوقيع.",
        "note_en": "There is no partial refund: burn() destroys the entire DGD balance. Verify the number before signing.",
    },
    "0x2a0c0dbecc7e4d658f48e01e3fa353f44050c208": {
        "title_ar": "IDEX 1.0 — أرصدة المودعين",
        "difficulty": "medium",
        "steps": [
            (
                "افتح صفحة العقد في Etherscan واختر Write Contract، ثم اربط المحفظة نفسها التي أودعت منها.",
                "Open the contract on Etherscan, switch to Write Contract and connect the wallet you deposited from.",
            ),
            (
                "نفّذ الدالة withdraw(address,uint256). الوسيط الأول: عنوان التوكن، أو 0x000...000 إذا كان الرصيد ETH.",
                "Call withdraw(address,uint256). First argument: the token address, or 0x000...000 for ETH.",
            ),
            (
                "الوسيط الثاني: المبلغ بوحدة الـ wei. اضرب الكمية بالعدد 10^decimals (18 للـ ETH).",
                "Second argument: the amount in wei (amount × 10^decimals, 18 for ETH).",
            ),
        ],
        "note_ar": "واجهة IDEX 1.0 أُغلقت، لكن العقد ما زال قابلاً للاستدعاء.",
        "note_en": "The IDEX 1.0 UI is gone; the contract itself still answers calls.",
    },
    "0x8d12a197cb00d4747a1fe03395095ce2a5cc6819": {
        "title_ar": "ForkDelta / EtherDelta v3",
        "difficulty": "medium",
        "steps": [
            (
                "اربط المحفظة في Etherscan ← Write Contract على عنوان العقد.",
                "Connect your wallet in Etherscan → Write Contract on the contract address.",
            ),
            (
                "للـ ETH: نفّذ withdraw(uint256) والمبلغ بالـ wei.",
                "For ETH: call withdraw(uint256) with the amount in wei.",
            ),
            (
                "لأي توكن: نفّذ withdrawToken(address,uint256) — عنوان التوكن ثم المبلغ بالـ wei.",
                "For a token: call withdrawToken(address,uint256) — token address, then amount in wei.",
            ),
        ],
        "note_ar": "الرصيد محفوظ في mapping داخل العقد، ولا علاقة له بواجهة الموقع الميتة.",
        "note_en": "Your balance lives in the contract's mapping; the dead website is irrelevant.",
    },
    "0x1ce7ae555139c5ef5a57cc8d814a867ee6ee33d8": {
        "title_ar": "Token.Store",
        "difficulty": "medium",
        "steps": [
            (
                "افتح العقد في Etherscan ← Write Contract واربط محفظتك.",
                "Open the contract in Etherscan → Write Contract and connect your wallet.",
            ),
            (
                "نفّذ withdraw(address,uint256): عنوان التوكن (أو 0x000...000 للـ ETH) ثم المبلغ بالـ wei.",
                "Call withdraw(address,uint256): token address (0x000...000 for ETH) then the amount in wei.",
            ),
        ],
        "note_ar": None,
        "note_en": None,
    },
    "0xbf4ed7b27f1d666546e30d74d50d173d20bca754": {
        "title_ar": "WithdrawDAO — استرداد الـ DAO",
        "difficulty": "medium",
        "steps": [
            (
                "تحتاج توكنات DAO (0xbb9bc244d798123fde783fcc1c72d3bb8c189413) في نفس المحفظة.",
                "You need DAO tokens (0xbb9bc244d798123fde783fcc1c72d3bb8c189413) in the same wallet.",
            ),
            (
                "أولاً approve: على عقد الـ DAO نفّذ approve(0xbf4e…a754, رصيدك).",
                "First approve: on the DAO token call approve(0xbf4e…a754, your balance).",
            ),
            (
                "ثم على عقد WithdrawDAO نفّذ withdraw().",
                "Then call withdraw() on the WithdrawDAO contract.",
            ),
            ("سعر الصرف: كل 100 DAO = 1 ETH.", "Rate: 100 DAO = 1 ETH."),
        ],
        "note_ar": "العقد جزء من حل الـ hard fork لعام 2016، وما زال يعمل.",
        "note_en": "Part of the 2016 hard-fork rescue contract; still functional.",
    },
    "0x0000000000b3f879cb30fe243b4dfee438691c04": {
        "title_ar": "GasToken2 (GST2)",
        "difficulty": "easy",
        "steps": [
            (
                "توكن الغاز هذا يُستبدل مجاناً مقابل خصم غاز: نفّذ free(uint256) على العقد نفسه.",
                "This gas token is redeemed for a gas refund: call free(uint256) on the token contract.",
            ),
            (
                "المبلغ بالـ wei (GST2 له 2 decimals فقط، فاحسب 10^2).",
                "Amount in base units (GST2 uses 2 decimals, so multiply by 10^2).",
            ),
        ],
        "note_ar": "الاسترداد يظهر كخصم على تكلفة الغاز في نفس المعاملة.",
        "note_en": "The refund is applied to the gas cost of the same transaction.",
    },
    "0x0000000000004946c0e9f43f4dee607b0ef1fa1c": {
        "title_ar": "CHI Gas Token",
        "difficulty": "easy",
        "steps": [
            (
                "نفّذ free(uint256) على عقد CHI لحرق التوكن مقابل خصم غاز.",
                "Call free(uint256) on the CHI contract to burn tokens for a gas refund.",
            ),
        ],
        "note_ar": "CHI له 2 decimals أيضاً.",
        "note_en": "CHI also uses 2 decimals.",
    },
    "0x89d24a6b4ccb1b6faa2625fe562bdd9a23260359": {
        "title_ar": "Old SAI (DAI القديم)",
        "difficulty": "hard",
        "steps": [
            (
                "SAI نسخة DAI القديمة. بوابة الترحيل إلى DAI أُغلقت منذ 2020.",
                "SAI is the legacy DAI. The migration gateway to DAI has been closed since 2020.",
            ),
            (
                "تحقق أولاً من وجود أي مسار في Maker: إذا أُغلق، فالتوكن بلا قيمة عملية الآن.",
                "Check whether any Maker redemption path is still open; if not, the token has no practical value now.",
            ),
        ],
        "note_ar": "تحذير: أي «خدمة استرداد» تطلب رسوماً مقدماً هي عملية نصب.",
        "note_en": "Warning: any 'recovery service' asking for an upfront fee is a scam.",
    },
}

# Check-type fallbacks when the address is not in the table above.
BY_CHECK_TYPE: dict[str, dict] = {
    "etherdelta": {
        "title_ar": "منصة تداول قديمة (EtherDelta style)",
        "difficulty": "medium",
        "steps": [
            (
                "افتح العقد في Etherscan ← Write Contract واربط المحفظة التي أودعت منها.",
                "Open the contract in Etherscan → Write Contract and connect the depositing wallet.",
            ),
            (
                "نفّذ withdraw(uint256) للـ ETH أو withdrawToken(address,uint256) للتوكنات.",
                "Call withdraw(uint256) for ETH, or withdrawToken(address,uint256) for tokens.",
            ),
        ],
        "note_ar": None,
        "note_en": None,
    },
    "erc20_self": {
        "title_ar": "رصيد داخل عقد توكن",
        "difficulty": "easy",
        "steps": [
            (
                "افتح عقد التوكن في Etherscan واربط محفظتك.",
                "Open the token contract in Etherscan and connect your wallet.",
            ),
            (
                "ابحث عن دالة redeem أو withdraw في تبويب Write Contract ونفّذها برصيدك.",
                "Find redeem or withdraw under Write Contract and call it with your balance.",
            ),
        ],
        "note_ar": None,
        "note_en": None,
    },
    "erc20_holder": {
        "title_ar": "استرداد مشروط بحيازة توكن",
        "difficulty": "medium",
        "steps": [
            (
                "تحتاج التوكن المذكور في نفس المحفظة للاستفادة من الاسترداد.",
                "You need the referenced token in the same wallet to qualify.",
            ),
            (
                "نفّذ approve ثم دالة السحب على العقد.",
                "Call approve, then the contract's withdraw function.",
            ),
        ],
        "note_ar": None,
        "note_en": None,
    },
    "digixdao": {
        "title_ar": "استرداد DAO مقابل ETH",
        "difficulty": "medium",
        "steps": [
            (
                "تحتاج التوكن الأصلي في نفس المحفظة، ثم approve لعقد الاسترداد.",
                "You need the original token in the same wallet, then approve the refund contract.",
            ),
            (
                "نفّذ burn() على عقد الاسترداد — يحرق التوكن ويرسل ETH.",
                "Call burn() on the refund contract — it burns the token and sends ETH.",
            ),
        ],
        "note_ar": "تحقق من السعر على السلسلة قبل التوقيع.",
        "note_en": "Verify the on-chain rate before signing.",
    },
}

CRYPTOPUNKS = {
    "title_ar": "CryptoPunks — مبالغ بيع غير مسحوبة",
    "difficulty": "easy",
    "steps": [
        (
            "هذا الرصيد ناتج عن بيع Punk ولم تُسحب قيمته. العقد: 0xb47e3cd837dDF8e4c57F05d70Ab865de6e193BBB",
            "This balance is from a Punk sale you never withdrew. Contract: 0xb47e3cd837dDF8e4c57F05d70Ab865de6e193BBB",
        ),
        (
            "افتح العقد في Etherscan ← Write Contract واربط المحفظة البائعة.",
            "Open the contract in Etherscan → Write Contract and connect the selling wallet.",
        ),
        (
            "نفّذ withdraw() بلا وسائط — تُحوَّل كل المبالغ المعلّقة إلى محفظتك.",
            "Call withdraw() with no arguments — every pending amount is sent to your wallet.",
        ),
    ],
    "note_ar": "الرصيد للبائع الأصلي فقط، ويُقرأ من دالة pendingWithdrawals(address).",
    "note_en": "Belongs to the original seller only; read from pendingWithdrawals(address).",
}

SCAM_WARNING = (
    "لا تشارك عبارة الاسترداد أو المفتاح الخاص مع أي جهة. كل خطوة أعلاه تنفّذها أنت من محفظتك.",
    "Never share your seed phrase or private key. Every step above is something you execute yourself.",
)


def guide_for(address: str, check_type: str | None, name: str | None = None) -> dict:
    """Return {title_ar, difficulty, steps, note_ar, note_en} for a finding."""
    entry = STEPS.get(address.lower())
    if entry:
        return entry
    if check_type == "cryptopunks":
        return CRYPTOPUNKS
    fallback = BY_CHECK_TYPE.get(check_type or "", BY_CHECK_TYPE["erc20_self"])
    if name:
        return {**fallback, "title_ar": f"{name} — {fallback['title_ar']}"}
    return fallback


def etherscan_url(address: str, is_token: bool = False) -> str:
    template = ETHERSCAN_TOKEN if is_token else ETHERSCAN
    return template.format(address=address)
