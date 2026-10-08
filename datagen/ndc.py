"""Synthetic NDCs and 10-to-11 digit normalization (5-4-2). Digits are random, never real products."""

from __future__ import annotations

import random
import re

FORMS = ("4-4-2", "5-3-2", "5-4-1")
_PADDED = (5, 4, 2)


def generate_ndc(rng: random.Random, form: str) -> str:
    if form not in FORMS:
        raise ValueError(f"unknown NDC form {form!r}")
    return "-".join("".join(str(rng.randrange(10)) for _ in range(int(w))) for w in form.split("-"))


def normalize_ndc(s: str) -> str:
    """Hyphenated 10-digit (4-4-2, 5-3-2, 5-4-1) or 11-digit (5-4-2 / plain) -> 11 plain digits."""
    if re.fullmatch(r"[0-9]{11}", s):
        return s
    m = re.fullmatch(r"([0-9]+)-([0-9]+)-([0-9]+)", s)
    if not m:
        raise ValueError(f"invalid NDC {s!r}")
    parts = m.groups()
    form = "-".join(str(len(p)) for p in parts)
    if form == "5-4-2":
        return "".join(parts)
    if form not in FORMS:
        raise ValueError(f"invalid NDC {s!r}")
    return "".join(p.zfill(w) for p, w in zip(parts, _PADDED, strict=True))
