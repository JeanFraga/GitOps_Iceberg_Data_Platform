"""FR-36 data drift injection: pluggable value-shift scenarios applied to a feed's base file.

The base file (the last file not produced by schema drift) is split: the base keeps the head of
its records and each data-drift scenario on that feed takes its own trailing chunk into
`<stem>_datadrift_<scenario><ext>` (same era) with the value shift applied. Schema-drift files
are left untouched.
"""

from __future__ import annotations

import csv
import json
import random
from collections.abc import Callable
from pathlib import PurePosixPath

from datagen.drift import DriftError, _Chunk, _parse, _serialise
from datagen.registry import DataFile


class DataDriftError(ValueError):
    """Bad data_drift target: unknown scenario, bad parameter, missing feed or field, unsupported format."""


def _get(chunk: _Chunk, r, field: str):
    return r[chunk.header.index(field)] if chunk.fmt == "csv" else r.get(field)


def _set(chunk: _Chunk, r, field: str, value) -> None:
    if chunk.fmt == "csv":
        r[chunk.header.index(field)] = value
    else:
        r[field] = value


def _num(value) -> float | None:
    if value is None or isinstance(value, bool) or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _int_like(value) -> bool:
    if isinstance(value, int):
        return True
    return isinstance(value, str) and value.strip().lstrip("-").isdigit()


def _typed(chunk: _Chunk, original, x: float, as_int: bool):
    """Format a shifted number: CSV as text, NDJSON keeps the numeric/string type of the original."""
    text = str(round(x)) if as_int else f"{x:.2f}"
    if chunk.fmt == "ndjson" and not isinstance(original, str):
        return round(x) if as_int else round(x, 2)
    return text


def _code_mix(chunk: _Chunk, t: dict, rng: random.Random) -> None:
    for r in chunk.records:
        _set(chunk, r, t["field"], rng.choice(list(t["codes"])))


def _null_rate(chunk: _Chunk, t: dict, rng: random.Random) -> None:
    n = len(chunk.records)
    picks = {i for i in range(n) if rng.random() < float(t["rate"])} or {rng.randrange(n)}
    for i in sorted(picks):
        _set(chunk, chunk.records[i], t["field"], "" if chunk.fmt == "csv" else None)


def _unit_scale(chunk: _Chunk, t: dict, rng: random.Random) -> None:
    for r in chunk.records:
        v = _get(chunk, r, t["field"])
        x = _num(v)
        if x is not None:
            _set(chunk, r, t["field"], _typed(chunk, v, x * float(t["factor"]), _int_like(v)))


def _amount_shift(chunk: _Chunk, t: dict, rng: random.Random) -> None:
    for r in chunk.records:
        v = _get(chunk, r, t["field"])
        x = _num(v)
        if x is not None:
            _set(chunk, r, t["field"], _typed(chunk, v, x * float(t["factor"]) * rng.uniform(0.9, 1.1), False))


SCENARIOS: dict[str, Callable[[_Chunk, dict, random.Random], None]] = {
    "code_mix": _code_mix,
    "null_rate": _null_rate,
    "unit_scale": _unit_scale,
    "amount_shift": _amount_shift,
}


def _positive(value) -> float | None:
    x = _num(value)
    return x if x is not None and x > 0 else None


def validate(targets) -> None:
    for t in targets:
        for key in ("scenario", "source", "feed", "field"):
            if not t.get(key):
                raise DataDriftError(f"data_drift target {t!r} missing {key}")
        s = t["scenario"]
        if s not in SCENARIOS:
            raise DataDriftError(f"unknown data drift scenario {s!r}")
        if _positive(t.get("magnitude")) is None:
            raise DataDriftError(f"{s} {t['source']}/{t['feed']} needs a positive 'magnitude'")
        if s == "code_mix":
            codes = t.get("codes")
            if not isinstance(codes, list | tuple) or not codes:
                raise DataDriftError(f"code_mix {t['source']}/{t['feed']} needs a non-empty 'codes' list")
        elif s == "null_rate":
            rate = _num(t.get("rate"))
            if rate is None or not 0 < rate <= 1:
                raise DataDriftError(f"null_rate {t['source']}/{t['feed']} needs 0 < 'rate' <= 1")
        else:
            factor = _positive(t.get("factor"))
            if factor is None or factor == 1:
                raise DataDriftError(f"{s} {t['source']}/{t['feed']} needs 'factor' > 0 and != 1")


def _base_index(files: list[DataFile]) -> int | None:
    idx = [i for i, f in enumerate(files) if "_drift_" not in f.name]
    return idx[-1] if idx else None


def check(targets, feed, files: list[DataFile]) -> None:
    """Validate that the feed's base file supports every target (format and field)."""
    i = _base_index(files)
    if i is None:
        raise DataDriftError(f"{feed.source}/{feed.feed}: no files to data-drift")
    try:
        fmt, _prefix, header, lines = _parse(files[i])
    except DriftError as exc:
        raise DataDriftError(f"{files[i].name}: unsupported format for data drift") from exc
    first = json.loads(lines[0]) if fmt == "ndjson" and lines else {}
    for t in targets:
        if not (t["field"] in header if fmt == "csv" else t["field"] in first):
            raise DataDriftError(f"{t['scenario']} {feed.source}/{feed.feed}: field {t['field']!r} not found")
    if len(targets) * max(1, len(lines) // 10) > len(lines):
        raise DataDriftError(f"{feed.source}/{feed.feed}: {len(lines)} records too few for data drift")


def _changed(before: list, after: list) -> int:
    return next(i for i, (a, b) in enumerate(zip(before, after, strict=True)) if a != b)


def apply(ctx, feed, files: list[DataFile]) -> tuple[list[DataFile], list[dict]]:
    """Split the feed's base file and apply each configured data-drift scenario to its own trailing chunk."""
    targets = [t for t in ctx.data_drift if t["source"] == feed.source and t["feed"] == feed.feed]
    if not targets:
        return list(files), []
    validate(targets)
    check(targets, feed, files)
    bi = _base_index(files)
    base = files[bi]
    fmt, prefix, header, lines = _parse(base)
    n, m = len(lines), len(targets)
    k = max(1, n // 10)
    stem, ext = PurePosixPath(base.name).stem, PurePosixPath(base.name).suffix
    head = lines[: n - m * k]
    out = list(files)
    out[bi] = DataFile(base.name, "".join(f"{x}\n" for x in prefix + head).encode(), len(head), base.era)
    entries = []
    for i, t in enumerate(targets):
        chunk_lines = lines[n - (m - i) * k : n - (m - i - 1) * k]
        if fmt == "csv":
            chunk = _Chunk(fmt, list(header), [list(r) for r in csv.reader(chunk_lines)])
        else:
            chunk = _Chunk(fmt, None, [json.loads(x) for x in chunk_lines])
        before = [repr(r) for r in chunk.records]
        rng = random.Random(f"{ctx.seed}:data_drift:{feed.source}:{feed.feed}:{t['scenario']}")
        SCENARIOS[t["scenario"]](chunk, t, rng)
        after = [repr(r) for r in chunk.records]
        if before == after:
            raise DataDriftError(f"{t['scenario']} {feed.source}/{feed.feed}: no value changed in {t['field']}")
        name = f"{stem}_datadrift_{t['scenario']}{ext}"
        out.append(DataFile(name, _serialise(chunk, prefix[0] if prefix else None), len(chunk.records), base.era))
        entries.append(
            {
                "scenario": t["scenario"],
                "source": feed.source,
                "feed": feed.feed,
                "file": f"landing/{feed.source}/{feed.feed}/{name}",
                "field": t["field"],
                "magnitude": t["magnitude"],
                "first_affected_record": _changed(before, after) + 1 + len(prefix),
            }
        )
    return out, entries
