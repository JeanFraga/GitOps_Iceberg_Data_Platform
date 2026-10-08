"""FR-3 schema drift injection: pluggable scenarios applied to a feed's latest-era file.

The target file is split: the base keeps the head of its records and each scenario on that
feed takes its own trailing chunk into `<stem>_drift_<scenario><ext>` with the drift applied.
"""

from __future__ import annotations

import csv
import io
import json
import random
import re
from collections.abc import Callable
from pathlib import PurePosixPath

from datagen.registry import DataFile


class DriftError(ValueError):
    """Bad schema_drift target: unknown scenario, unsupported format, missing feed or field."""


_ISO = re.compile(r"^(\d{4})-(\d{2})-(\d{2})$")


class _Chunk:
    """Records of one chunk in a format-neutral shape: CSV rows (lists) or JSON objects (dicts)."""

    def __init__(self, fmt: str, header: list[str] | None, records: list):
        self.fmt, self.header, self.records = fmt, header, records


def _rename(chunk: _Chunk, t: dict, rng: random.Random) -> int:
    to = t["to"]
    field = t["field"]
    if chunk.fmt == "csv":
        chunk.header = [to if h == field else h for h in chunk.header]
    else:
        chunk.records = [{(to if k == field else k): v for k, v in r.items()} for r in chunk.records]
    return 0


def _add(chunk: _Chunk, t: dict, rng: random.Random) -> int:
    field = t["field"]
    values = [f"PA{rng.randrange(10**8):08d}" for _ in chunk.records]
    if chunk.fmt == "csv":
        chunk.header = [*chunk.header, field]
        chunk.records = [[*r, v] for r, v in zip(chunk.records, values, strict=True)]
    else:
        chunk.records = [{**r, field: v} for r, v in zip(chunk.records, values, strict=True)]
    return 0


def _remove(chunk: _Chunk, t: dict, rng: random.Random) -> int:
    field = t["field"]
    if chunk.fmt == "csv":
        i = chunk.header.index(field)
        chunk.header = chunk.header[:i] + chunk.header[i + 1 :]
        chunk.records = [r[:i] + r[i + 1 :] for r in chunk.records]
    else:
        chunk.records = [{k: v for k, v in r.items() if k != field} for r in chunk.records]
    return 0


def _reformat(value):
    m = _ISO.match(value) if isinstance(value, str) else None
    return f"{m[2]}/{m[3]}/{m[1]}" if m else value


def _date_format(chunk: _Chunk, t: dict, rng: random.Random) -> int:
    field = t["field"]
    first = None
    if chunk.fmt == "csv":
        i = chunk.header.index(field)
        for n, r in enumerate(chunk.records):
            new = _reformat(r[i])
            if new != r[i] and first is None:
                first = n
            r[i] = new
    else:
        for n, r in enumerate(chunk.records):
            if field in r:
                new = _reformat(r[field])
                if new != r[field] and first is None:
                    first = n
                r[field] = new
    if first is None:
        raise DriftError(f"date_format {t['source']}/{t['feed']}: no YYYY-MM-DD value in {t['field']}")
    return first


def _cast_failure(chunk: _Chunk, t: dict, rng: random.Random) -> int:
    field = t["field"]
    n = len(chunk.records)
    picks = sorted({i for i in range(n) if rng.random() < 0.2} or {rng.randrange(n)})
    for i in picks:
        if chunk.fmt == "csv":
            chunk.records[i][chunk.header.index(field)] = "N/A"
        else:
            chunk.records[i][field] = "N/A"
    return picks[0]


SCENARIOS: dict[str, Callable[[_Chunk, dict, random.Random], int]] = {
    "rename_column": _rename,
    "add_column": _add,
    "remove_column": _remove,
    "date_format": _date_format,
    "cast_failure": _cast_failure,
}


def _parse(f: DataFile) -> tuple[str, list[str], list[str] | None, list[str]]:
    """(fmt, prefix lines, csv header, record lines) of a data file."""
    suffix = PurePosixPath(f.name).suffix
    lines = f.content.decode().split("\n")
    if lines and lines[-1] == "":
        lines.pop()
    if suffix == ".csv":
        if len(lines) < 2 or not lines[0].startswith("# "):
            raise DriftError(f"{f.name}: CSV without marker line and header")
        return "csv", lines[:2], next(csv.reader([lines[1]])), lines[2:]
    if suffix == ".ndjson":
        return "ndjson", [], None, lines
    raise DriftError(f"{f.name}: unsupported format for schema drift")


def _serialise(chunk: _Chunk, marker: str | None) -> bytes:
    if chunk.fmt == "csv":
        buf = io.StringIO()
        buf.write(marker + "\n")
        w = csv.writer(buf, lineterminator="\n")
        w.writerow(chunk.header)
        w.writerows(chunk.records)
        return buf.getvalue().encode()
    return "".join(json.dumps(r, separators=(",", ":")) + "\n" for r in chunk.records).encode()


def validate(targets) -> None:
    for t in targets:
        for key in ("scenario", "source", "feed", "field"):
            if not t.get(key):
                raise DriftError(f"schema_drift target {t!r} missing {key}")
        if t["scenario"] not in SCENARIOS:
            raise DriftError(f"unknown schema drift scenario {t['scenario']!r}")
        if t["scenario"] == "rename_column" and not t.get("to"):
            raise DriftError(f"rename_column {t['source']}/{t['feed']} needs 'to'")


def apply(ctx, feed, files: list[DataFile]) -> tuple[list[DataFile], list[dict]]:
    """Split the feed's last file and apply each configured scenario to its own trailing chunk."""
    targets = [t for t in ctx.schema_drift if t["source"] == feed.source and t["feed"] == feed.feed]
    if not targets:
        return list(files), []
    validate(targets)
    if not files:
        raise DriftError(f"{feed.source}/{feed.feed}: no files to drift")
    base = files[-1]
    fmt, prefix, header, lines = _parse(base)
    first_rec = json.loads(lines[0]) if fmt == "ndjson" and lines else {}
    for t in targets:
        present = t["field"] in header if fmt == "csv" else t["field"] in first_rec
        if t["scenario"] == "add_column" and present:
            raise DriftError(f"add_column {feed.source}/{feed.feed}: field {t['field']!r} already exists")
        if t["scenario"] != "add_column" and not present:
            raise DriftError(f"{t['scenario']} {feed.source}/{feed.feed}: field {t['field']!r} not found")
    n, m = len(lines), len(targets)
    k = max(1, n // 10)
    if m * k > n:
        raise DriftError(f"{feed.source}/{feed.feed}: {n} records too few for {m} drift scenarios")
    stem, ext = PurePosixPath(base.name).stem, PurePosixPath(base.name).suffix
    head = lines[: n - m * k]
    out = [*files[:-1], DataFile(base.name, "".join(f"{x}\n" for x in prefix + head).encode(), len(head), base.era)]
    entries = []
    for i, t in enumerate(targets):
        chunk_lines = lines[n - (m - i) * k : n - (m - i - 1) * k]
        if fmt == "csv":
            chunk = _Chunk(fmt, list(header), [list(r) for r in csv.reader(chunk_lines)])
        else:
            chunk = _Chunk(fmt, None, [json.loads(x) for x in chunk_lines])
        rng = random.Random(f"{ctx.seed}:drift:{feed.source}:{feed.feed}:{t['scenario']}")
        idx = SCENARIOS[t["scenario"]](chunk, t, rng)
        name = f"{stem}_drift_{t['scenario']}{ext}"
        out.append(DataFile(name, _serialise(chunk, prefix[0] if prefix else None), len(chunk.records), base.era))
        entries.append(
            {
                "scenario": t["scenario"],
                "source": feed.source,
                "feed": feed.feed,
                "file": f"landing/{feed.source}/{feed.feed}/{name}",
                "field": t["field"],
                "first_affected_record": idx + 1 + len(prefix),
            }
        )
    return out, entries
