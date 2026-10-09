"""Raw X12 bytes -> JSONL bytes, one line per segment (AD-4 pre-parse derivative).

Reuses ingestion.records.split(data, "x12") for the ISA16 split and segment ordinals and
records.x12_element_separator for ISA byte 4. Output is byte-deterministic: sorted keys,
compact separators, UTF-8, LF line ends, no timestamps, run ids or absolute paths.
"""

from __future__ import annotations

import hashlib
import json

from ingestion.records import split, x12_element_separator

KEYS = ("source_file", "source_sha256", "isa_control", "gs_control", "st_control", "segment_id",
        "segment_ordinal", "elements")  # fmt: skip


def _el(elements: list[str], i: int) -> str | None:
    return elements[i].strip() if len(elements) > i else None


def preparse(data: bytes, name: str) -> bytes:
    """`name` is the file's base name (never a path). Raises ValueError on input without a full ISA."""
    records = split(data, "x12")
    sep = x12_element_separator(records[0].raw)
    sha = hashlib.sha256(data).hexdigest()
    isa = gs = st = None
    out: list[str] = []
    for rec in records:
        if rec.encoding != "utf-8":  # raw kept as base64, as in Bronze; no element split
            seg = rec.raw.split(sep.encode("utf-8"), 1)[0].decode("ascii", errors="replace").strip()
            row = {"source_file": name, "source_sha256": sha, "isa_control": isa, "gs_control": gs,
                   "st_control": st, "segment_id": seg, "segment_ordinal": rec.ordinal, "elements": None,
                   "encoding": rec.encoding, "raw_b64": rec.raw_line}  # fmt: skip
            out.append(json.dumps(row, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n")
            continue
        elements = rec.raw.decode("utf-8").split(sep)
        seg = elements[0].strip()
        if seg == "ISA":
            isa, gs, st = _el(elements, 13), None, None
        elif seg == "GS":
            gs, st = _el(elements, 6), None
        elif seg == "ST":
            st = _el(elements, 2)
        row = {"source_file": name, "source_sha256": sha, "isa_control": isa,
               "gs_control": gs if seg not in ("ISA", "IEA") else None,
               "st_control": st if seg not in ("ISA", "IEA", "GS", "GE") else None,
               "segment_id": seg, "segment_ordinal": rec.ordinal, "elements": elements}  # fmt: skip
        out.append(json.dumps(row, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n")
        if seg == "SE":
            st = None
        elif seg == "GE":
            gs, st = None, None
        elif seg == "IEA":
            isa, gs, st = None, None, None
    return "".join(out).encode("utf-8")
