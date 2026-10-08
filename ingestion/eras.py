"""AD-5 era routing: (source, feed, fingerprint, columns) -> known era, additive era or unmapped_<fp8>.

The registry is config/eras/<source>.yaml (feed -> era -> {fingerprint, columns}); fingerprints
come only from config/fingerprint.py (AD-22). Eras are never inferred from dates or file names.

Additive: the file's ordered columns contain a mapped era's columns as an in-order subsequence,
plus at least one extra column. When several eras qualify, the one with the most columns wins;
a tie routes to unmapped. A reorder, rename or removal is a new fingerprint and goes to unmapped.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml

from config.fingerprint import fp8

ERAS_DIR = Path(__file__).resolve().parent.parent / "config" / "eras"
KNOWN, ADDITIVE, UNMAPPED = "known", "additive", "unmapped"


@dataclass(frozen=True)
class Route:
    era: str
    kind: str  # known | additive | unmapped
    added: list[str] = field(default_factory=list)  # columns beyond the base era (additive only)


def registry(source: str, eras_dir: Path = ERAS_DIR) -> dict:
    path = eras_dir / f"{source}.yaml"
    return (yaml.safe_load(path.read_text()) or {}) if path.is_file() else {}


def _is_subsequence(base: list[str], cols: list[str]) -> bool:
    it = iter(cols)
    return all(c in it for c in base)


def resolve(source: str, feed: str, fp: str, columns: list[str], eras_dir: Path = ERAS_DIR) -> Route:
    eras = {str(k): v for k, v in (registry(source, eras_dir).get(feed) or {}).items()}
    for era, entry in eras.items():
        if entry["fingerprint"] == fp:
            return Route(era, KNOWN)
    supersets = [
        (era, entry["columns"])
        for era, entry in eras.items()
        if len(columns) > len(entry["columns"]) and _is_subsequence(entry["columns"], columns)
    ]
    if supersets:
        width = max(len(c) for _, c in supersets)
        best = [(era, c) for era, c in supersets if len(c) == width]
        if len(best) == 1:
            era, base = best[0]
            return Route(era, ADDITIVE, [c for c in columns if c not in set(base)])
    return Route(f"unmapped_{fp8(fp).lower()}", UNMAPPED)
