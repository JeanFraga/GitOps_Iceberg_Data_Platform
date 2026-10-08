"""AD-4 reconcile gate: landing records vs Bronze branch rows. Pure Python, no Spark.

Compares the record count and the per-record SHA-256, aligned on `_line_ordinal`. The result
carries counts, hashes and ordinals only, never row values.
"""

from __future__ import annotations

import base64
import hashlib
from collections.abc import Iterable
from dataclasses import dataclass, field

from ingestion.records import Record

REASON = "RECONCILE_FAIL"


@dataclass(frozen=True)
class GateResult:
    passed: bool
    expected: int
    actual: int
    mismatches: int = 0
    first_mismatch_ordinal: int | None = None
    detail: dict = field(default_factory=dict)


def row_bytes(raw_line: str | None, encoding: str | None) -> bytes:
    """Bytes a Bronze row claims to carry: base64-decoded when `_raw_encoding` is not utf-8."""
    if raw_line is None:
        return b""
    if encoding == "utf-8":
        return raw_line.encode("utf-8")
    return base64.b64decode(raw_line)


def gate(records: list[Record], branch_rows: Iterable[tuple[int, str | None, str | None]]) -> GateResult:
    """records: landing data records; branch_rows: (_line_ordinal, _raw_line, _raw_encoding) of this run."""
    rows = list(branch_rows)
    expected, actual = len(records), len(rows)
    if expected != actual:
        return GateResult(False, expected, actual, detail={"check": "count", "expected": expected, "actual": actual})
    want = {r.ordinal: hashlib.sha256(r.raw).hexdigest() for r in records}
    got: dict[int, str] = {}
    dup = 0
    for ordinal, raw_line, encoding in rows:
        if ordinal in got:
            dup += 1
        got[ordinal] = hashlib.sha256(row_bytes(raw_line, encoding)).hexdigest()
    bad = sorted(o for o in want.keys() | got.keys() if want.get(o) != got.get(o))
    mismatches = len(bad) + dup
    if mismatches:
        first = bad[0] if bad else None
        return GateResult(False, expected, actual, mismatches, first,
                          {"check": "hash", "expected": expected, "actual": actual, "mismatches": mismatches,
                           "first_mismatch_ordinal": first})  # fmt: skip
    return GateResult(True, expected, actual, detail={"check": "pass", "expected": expected, "actual": actual})
