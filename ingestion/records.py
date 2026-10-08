"""AD-4 record split per config/standards/records.yaml. Pure Python, no Spark."""

from __future__ import annotations

import base64
from dataclasses import dataclass
from functools import cache
from pathlib import Path

import yaml

RULES_PATH = Path(__file__).resolve().parent.parent / "config" / "standards" / "records.yaml"
BOM = b"\xef\xbb\xbf"


@cache
def rules() -> dict:
    return yaml.safe_load(RULES_PATH.read_text())


@dataclass(frozen=True)
class Record:
    ordinal: int  # 1-based physical line (csv/jsonl) or segment (x12) where the record starts
    raw: bytes  # record bytes without the terminator

    @property
    def encoding(self) -> str:
        try:
            self.raw.decode("utf-8")
        except UnicodeDecodeError:
            return rules()["encoding"]["fallback"]
        return "utf-8"

    @property
    def raw_line(self) -> str:
        """Exact text, or base64 of the bytes when not UTF-8 (see `encoding`)."""
        if self.encoding == "utf-8":
            return self.raw.decode("utf-8")
        return base64.b64encode(self.raw).decode("ascii")


def strip_bom(data: bytes) -> bytes:
    return data[len(BOM) :] if rules()["strip_bom"] and data.startswith(BOM) else data


def _split_lf(data: bytes, quoted: bool) -> list[Record]:
    out: list[Record] = []
    line, start, in_quotes, buf_start = 1, 1, False, 0
    field_start = True  # RFC 4180: a quote opens quoting only at the start of a field
    i, n = 0, len(data)
    while i < n:
        byte = data[i]
        if quoted and in_quotes:
            if byte == 0x22:
                if i + 1 < n and data[i + 1] == 0x22:
                    i += 1  # "" escape inside quotes
                else:
                    in_quotes = False
            elif byte == 0x0A:
                line += 1
        elif quoted and byte == 0x22 and field_start:
            in_quotes = True
        elif byte == 0x0A:
            out.append(Record(start, data[buf_start:i].removesuffix(b"\r")))
            buf_start, start = i + 1, line + 1
            line += 1
        field_start = not in_quotes and byte in (0x2C, 0x0A)
        i += 1
    if buf_start < len(data):
        out.append(Record(start, data[buf_start:].removesuffix(b"\r")))
    return out


def _split_x12(data: bytes) -> list[Record]:
    if not data.startswith(b"ISA") or len(data) < 106:
        raise ValueError("X12 input must start with a full ISA segment")
    term = data[105:106]
    segs = [s.strip(b"\r\n") for s in data.split(term)]
    return [Record(i, s) for i, s in enumerate((s for s in segs if s), start=1)]


def split(data: bytes, file_format: str) -> list[Record]:
    """Split BOM-stripped bytes into records per records.yaml."""
    spec = rules()["formats"][file_format]
    data = strip_bom(data)
    if spec["split"] == "ISA16":
        return _split_x12(data)
    return _split_lf(data, quoted=spec["quoting"] == "rfc4180")
