"""AD-22 schema fingerprint: the one implementation used by the Bronze loader and the onboarding CLI.

Spec and golden vectors: config/standards/fingerprint.yaml.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import unicodedata

JSONL_SAMPLE_RECORDS = 100  # N in the spec; must match fingerprint.yaml


def _digest(layout: list[str]) -> str:
    return hashlib.sha256("\n".join(layout).encode("utf-8")).hexdigest()


def csv_layout(text: str) -> list[str]:
    """Ordered header names: NFC, trimmed, lowercased. A leading BOM is ignored."""
    header = next(csv.reader(io.StringIO(text.lstrip("\ufeff"))), [])
    if not header:
        raise ValueError("CSV input has no header row")
    return [unicodedata.normalize("NFC", name).strip().lower() for name in header]


def jsonl_layout(text: str, sample: int = JSONL_SAMPLE_RECORDS) -> list[str]:
    """Sorted set of top-level keys across the first `sample` non-blank records."""
    keys: set[str] = set()
    # Records split on LF only (records.yaml); U+2028 etc. are legal inside JSON strings.
    lines = (line.removesuffix("\r") for line in text.lstrip("\ufeff").split("\n"))
    records = (line for line in lines if line.strip())
    for i, line in enumerate(records):
        if i >= sample:
            break
        record = json.loads(line)
        if not isinstance(record, dict):
            raise TypeError(f"JSONL record {i} is not an object")
        keys.update(record)
    return sorted(keys)


def x12_layout(text: str) -> list[str]:
    """Distinct segment ids, in first-occurrence order, of the first ST..SE transaction set.

    Separators come from the ISA segment: element separator at offset 3, segment terminator
    (ISA16) right after the 16th element. Repeated loops do not change the layout.
    """
    text = text.lstrip("\ufeff")
    if not text.startswith("ISA") or len(text) < 106:
        raise ValueError("X12 input must start with a full ISA segment")
    element_sep, terminator = text[3], text[105]
    layout: list[str] = []
    in_set = False
    for raw in text.split(terminator):
        seg_id = raw.strip().split(element_sep, 1)[0]
        if seg_id == "ST":
            in_set = True
        if in_set and seg_id not in layout:
            layout.append(seg_id)
        if in_set and seg_id == "SE":
            return layout
    raise ValueError("X12 input has no complete ST..SE transaction set")


LAYOUTS = {"csv": csv_layout, "jsonl": jsonl_layout, "x12": x12_layout}


def fingerprint(text: str, file_format: str) -> str:
    """SHA-256 lowercase hex of the format's layout joined by newlines."""
    return _digest(LAYOUTS[file_format](text))


def fp8(fingerprint_hex: str) -> str:
    return fingerprint_hex[:8]
