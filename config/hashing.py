"""AD-7 hash specification, Python reference implementation.

Spec and golden vectors: config/standards/hashing.yaml. Every engine (Spark, dbt,
MPI) must reproduce those vectors; this module is the Python side.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import unicodedata
from decimal import Decimal

NULL_SENTINEL = "^^"
DELIMITER = "||"
ASCII_WS = " \t\n\r\x0b\x0c"


class AllNullBusinessKeyError(ValueError):
    """Every business-key component is NULL or empty; the row cannot get a hash key."""


def canonical(value: object) -> str | None:
    """Canonical string form of one value, before normalization."""
    if value is None:
        return None
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, dt.datetime):
        if value.tzinfo is None:
            raise ValueError("timestamps must be timezone-aware; convert to UTC before hashing")
        return value.astimezone(dt.UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    if isinstance(value, dt.date):
        return value.isoformat()
    if isinstance(value, Decimal):
        if not value.is_finite():
            raise ValueError("NaN and infinite decimals are not hashable under AD-7")
        text = format(value.normalize(), "f")
        return "0" if text in ("-0", "0") else text
    if isinstance(value, float):
        raise TypeError("floats are not hashable under AD-7; use Decimal")
    return str(value)


def normalize(value: object, business_key: bool) -> str:
    """NFC, ASCII-whitespace trim, uppercase for business keys, empty/NULL -> sentinel, escape."""
    text = canonical(value)
    if text is None:
        return NULL_SENTINEL
    text = unicodedata.normalize("NFC", text).strip(ASCII_WS)
    if text == "":
        return NULL_SENTINEL
    if business_key:
        text = "".join(c.upper() if c.isascii() else c for c in text)
    return text.replace("\\", "\\\\").replace("|", "\\|")


def hash_input(values: list[object], business_key: bool) -> str:
    parts = [normalize(v, business_key) for v in values]
    if business_key and all(p == NULL_SENTINEL for p in parts):
        raise AllNullBusinessKeyError("all business-key components are NULL")
    return DELIMITER.join(parts)


def hash_key(values: list[object]) -> str:
    """Hub/link hash key: ordered business-key components (qualifier first)."""
    return hashlib.md5(hash_input(values, True).encode("utf-8")).hexdigest().upper()


def hashdiff(values: list[object]) -> str:
    """Satellite hashdiff: payload columns in config order, no case folding."""
    return hashlib.md5(hash_input(values, False).encode("utf-8")).hexdigest().upper()
