"""Exact calldata for recovering a detected balance.

We build the same transaction a user would type into a wallet's "custom
calldata" screen or Etherscan's Write Contract tab. Nothing here signs, sends,
or stores a key: it is a hex string the user reviews and signs from their own
wallet.

Every selector below is ``keccak256(signature)[:4]`` and is pinned in
``tests/test_calldata.py`` with golden vectors, so a typo cannot ship silently.
"""

from __future__ import annotations

from typing import Any, Optional

ZERO = "0x0000000000000000000000000000000000000000"

SELECTORS: dict[str, str] = {
    "withdraw()": "0x3ccfd60b",
    "withdraw(uint256)": "0x2e1a7d4d",
    "withdraw(address,uint256)": "0xf3fef3a3",
    "withdrawToken(address,uint256)": "0x9e281a98",
    "redeem(uint256)": "0xdb006a75",
    "free(uint256)": "0xd8ccd0f3",
    "approve(address,uint256)": "0x095ea7b3",
    "burn()": "0x44df8e70",
}

_ETH_KINDS = {"etherdelta", "idex"}


def encode_address(address: str) -> str:
    """ABI-encode one address as a 32-byte word."""
    value = address.strip().lower()
    if not value.startswith("0x") or len(value) != 42:
        raise ValueError(f"not an address: {address!r}")
    int(value[2:], 16)
    return "0" * 24 + value[2:]


def encode_uint(value: int) -> str:
    """ABI-encode a uint256, rejecting negatives and overflow."""
    if value < 0:
        raise ValueError("uint256 cannot be negative")
    if value >= 2**256:
        raise ValueError("uint256 overflow")
    return f"{value:064x}"


def encode_call(signature: str, *words: str) -> str:
    """Return selector + pre-encoded words."""
    try:
        selector = SELECTORS[signature]
    except KeyError as exc:
        raise ValueError(f"unpinned selector: {signature}") from exc
    return selector + "".join(words)


def _step(
    function: str,
    to: str,
    data: str,
    label_ar: str,
    label_en: str,
    *,
    value: str = "0x0",
) -> dict[str, Any]:
    return {
        "function": function,
        "to": to,
        "data": data,
        "value": value,
        "label_ar": label_ar,
        "label_en": label_en,
    }


def build_steps(
    kind: Optional[str],
    *,
    contract: str,
    token: str = ZERO,
    amount_raw: int = 0,
    source_token: Optional[str] = None,
    source_raw: Optional[int] = None,
) -> list[dict[str, Any]]:
    """Build the ordered transaction steps for one finding.

    ``amount_raw`` is the amount the target function expects. For ETH claims
    (DigixDAO) it is the ETH claim in wei; ``source_raw`` is the token amount
    that must be approved first.
    """
    if not kind or kind == "none":
        return []

    if kind == "cryptopunks":
        return [
            _step(
                "withdraw()",
                contract,
                encode_call("withdraw()"),
                "استدعِ withdraw() على عقد CryptoPunks — يرسل كل المبالغ المعلّقة لمحفظتك.",
                "Call withdraw() on the CryptoPunks contract — pays every pending amount to your wallet.",
            )
        ]

    if kind == "etherdelta":
        if token == ZERO:
            return [
                _step(
                    "withdraw(uint256)",
                    contract,
                    encode_call("withdraw(uint256)", encode_uint(amount_raw)),
                    "استدعِ withdraw(uint256) على العقد لسحب رصيد ETH بالكامل.",
                    "Call withdraw(uint256) on the contract to withdraw the full ETH balance.",
                )
            ]
        return [
            _step(
                "withdrawToken(address,uint256)",
                contract,
                encode_call(
                    "withdrawToken(address,uint256)",
                    encode_address(token),
                    encode_uint(amount_raw),
                ),
                "استدعِ withdrawToken(address,uint256) لسحب رصيد التوكن.",
                "Call withdrawToken(address,uint256) to withdraw the token balance.",
            )
        ]

    if kind == "idex":
        return [
            _step(
                "withdraw(address,uint256)",
                contract,
                encode_call(
                    "withdraw(address,uint256)",
                    encode_address(token),
                    encode_uint(amount_raw),
                ),
                "استدعِ withdraw(address,uint256) — الوسيط الأول عنوان التوكن أو 0x0 للـ ETH.",
                "Call withdraw(address,uint256) — first argument is the token address, or 0x0 for ETH.",
            )
        ]

    if kind == "gastoken":
        return [
            _step(
                "free(uint256)",
                contract,
                encode_call("free(uint256)", encode_uint(amount_raw)),
                "استدعِ free(uint256) لحرق التوكن واسترداد خصم الغاز.",
                "Call free(uint256) to burn the token and claim the gas refund.",
            )
        ]

    if kind == "withdrawdao":
        return [
            _step(
                "approve(address,uint256)",
                token,
                encode_call(
                    "approve(address,uint256)",
                    encode_address(contract),
                    encode_uint(amount_raw),
                ),
                "على عقد DAO: نفّذ approve(WithdrawDAO, رصيدك) أولاً.",
                "On the DAO token: call approve(WithdrawDAO, your balance) first.",
            ),
            _step(
                "withdraw()",
                contract,
                encode_call("withdraw()"),
                "ثم على WithdrawDAO: نفّذ withdraw() — كل 100 DAO = 1 ETH.",
                "Then on WithdrawDAO: call withdraw() — 100 DAO = 1 ETH.",
            ),
        ]

    if kind == "digixdao":
        if not source_token or source_raw is None:
            raise ValueError("digixdao needs the DGD token address and raw balance")
        return [
            _step(
                "approve(address,uint256)",
                source_token,
                encode_call(
                    "approve(address,uint256)",
                    encode_address(contract),
                    encode_uint(source_raw),
                ),
                "على عقد DGD: نفّذ approve(Acid, كامل رصيدك) أولاً.",
                "On the DGD token: call approve(Acid, your full balance) first.",
            ),
            _step(
                "burn()",
                contract,
                encode_call("burn()"),
                "ثم على Acid: نفّذ burn() — يحرق كل DGD ويرسل ETH فوراً.",
                "Then on Acid: call burn() — burns all DGD and sends the ETH immediately.",
            ),
        ]

    raise ValueError(f"unknown calldata kind: {kind}")
