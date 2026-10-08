"""Write deterministic output: landing files, ground-truth JSONL, manifest and names list."""

from __future__ import annotations

import hashlib
import json
import shutil
from dataclasses import dataclass, field
from pathlib import Path

from datagen import population, registry

OUT = Path(__file__).resolve().parent / "out"
BASE_YEAR = 2024
TRUTH_TABLES = ("person_truth", "coverage_spans", "encounter_claim")


@dataclass
class Context:
    seed: int
    volume_name: str
    volume: dict
    token: str
    _built: dict[int, tuple[population.Household, ...]] = field(default_factory=dict, repr=False)

    @property
    def years(self) -> list[int]:
        return [BASE_YEAR + i for i in range(self.volume["years"])]

    def population(self, persons: int) -> tuple[population.Household, ...]:
        """Shared seeded population; feeds asking for the same size get the same households."""
        if persons not in self._built:
            self._built[persons] = tuple(population.build(self.seed, persons))
        return self._built[persons]


def _jsonl(rows: list[dict], token: str, seed: int) -> bytes:
    if not rows:
        return (json.dumps({"_synthetic": token}) + "\n").encode()
    full = [{"_synthetic": token, "generator_seed": seed, **r} for r in rows]
    lines = sorted(json.dumps(r, sort_keys=False) for r in full)
    return ("\n".join(lines) + "\n").encode()


def generate(ctx: Context, out: Path = OUT, feeds: list[registry.Feed] | None = None) -> dict:
    if out.exists():
        shutil.rmtree(out)
    truth: dict[str, list[dict]] = {t: [] for t in TRUTH_TABLES}
    files, names = [], set()
    for feed in feeds if feeds is not None else registry.discover():
        result = feed.generate(ctx)
        for f in result.files:
            rel = Path("landing") / feed.source / feed.feed / f.name
            (out / rel).parent.mkdir(parents=True, exist_ok=True)
            (out / rel).write_bytes(f.content)
            files.append(
                {
                    "path": rel.as_posix(),
                    "source": feed.source,
                    "feed": feed.feed,
                    "sha256": hashlib.sha256(f.content).hexdigest(),
                    "records": f.records,
                }
            )
        for t in TRUTH_TABLES:
            truth[t] += getattr(result, t)
    for hh in (hh for built in ctx._built.values() for hh in built):
        names.update(f"{p.first_name} {p.last_name}" for p in hh.members)
    (out / "ground_truth").mkdir(parents=True, exist_ok=True)
    for t, rows in truth.items():
        (out / "ground_truth" / f"{t}.jsonl").write_bytes(_jsonl(rows, ctx.token, ctx.seed))
    manifest = {
        "_synthetic": ctx.token,
        "seed": ctx.seed,
        "volume_profile": ctx.volume_name,
        "files": sorted(files, key=lambda f: f["path"]),
        "schema_drift": [],
        "data_drift": [],
    }
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    (out / "names.txt").write_text("".join(f"{n}\n" for n in sorted(names)))
    return manifest
