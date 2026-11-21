"""Shared helpers used across the scanner and the audit product."""

from __future__ import annotations

import re
from typing import Any

ADDRESS_RE = re.compile(r"^0x[0-9a-fA-F]{40}$")
ZERO_ADDRESS = "0x" + "00" * 20


class Colors:
    """ANSI escapes for terminal output (no dependency on colorama)."""

    RESET = "\033[0m"
    BOLD = "\033[1m"
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    RED = "\033[31m"
    BLUE = "\033[34m"
    CYAN = "\033[36m"
    GRAY = "\033[90m"
    MAGENTA = "\033[35m"


def normalize_address(address: Any) -> str:
    """Validate an EVM address and return it lower-cased.

    Raises ValueError for anything that is not 0x followed by 40 hex chars.
    """
    if not isinstance(address, str):
        raise ValueError("address must be a string")
    address = address.strip()
    if not ADDRESS_RE.match(address):
        raise ValueError(f"invalid EVM address: {address!r}")
    return address.lower()


def encode_addr(address: str) -> str:
    """ABI-encode an address as a 32-byte word (no 0x prefix)."""
    return ("0" * 24) + address.lower().replace("0x", "")


def encode_uint(value: int) -> str:
    """ABI-encode an unsigned integer as a 32-byte word (no 0x prefix)."""
    if value < 0:
        raise ValueError("cannot encode a negative integer")
    return format(value, "064x")


def selector_call(selector: str, *words: str) -> str:
    """Build eth_call data from a 4-byte selector plus pre-encoded words."""
    head = selector.lower()
    if not head.startswith("0x"):
        head = "0x" + head
    return head + "".join(words)


def short_addr(address: str, head: int = 6, tail: int = 4) -> str:
    """0x1234...abcd style shortening for display."""
    if not address or len(address) <= head + tail + 1:
        return address
    return f"{address[:head]}\u2026{address[-tail:]}"


def wei_to_float(raw: int | str, decimals: int = 18) -> float:
    """Convert a base-unit integer (or its hex/decimal string) to a float."""
    if isinstance(raw, str):
        raw = int(raw, 16) if raw.startswith("0x") else int(raw)
    return raw / (10**decimals)


def format_amount(value: float, places: int = 6) -> str:
    """Human-friendly amount: thousands separators, trailing zeros trimmed."""
    if value == 0:
        return "0"
    if value < 1e-6:
        return "<0.000001"
    text = f"{value:,.{places}f}"
    return text.rstrip("0").rstrip(".") if "." in text else text
