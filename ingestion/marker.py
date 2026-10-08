"""NFR-4 / AD-14: refuse an unmarked file; drop the CSV marker line before fingerprinting."""

from __future__ import annotations

from functools import cache
from pathlib import Path

import yaml

from ingestion.records import Record, strip_bom

GUARDRAILS = Path(__file__).resolve().parent.parent / "config" / "standards" / "guardrails.yaml"


class UnmarkedFile(Exception):
    """The landed object has no synthetic marker within the configured prefix."""


@cache
def marker_rule() -> tuple[str, int]:
    rule = yaml.safe_load(GUARDRAILS.read_text())["synthetic_marker"]
    return rule["token"], int(rule["within_bytes"])


def check_marker(data: bytes) -> None:
    token, within = marker_rule()
    if token.encode("utf-8") not in strip_bom(data)[:within]:
        raise UnmarkedFile(f"no synthetic marker within the first {within} bytes")


def drop_marker_line(records: list[Record]) -> list[Record]:
    """Drop record 1 when it is a `#` comment line carrying the marker token."""
    token, _ = marker_rule()
    if records and records[0].raw.startswith(b"#") and token.encode("utf-8") in records[0].raw:
        return records[1:]
    return records
