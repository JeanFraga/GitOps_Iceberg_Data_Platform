"""CI check: regenerate every X12 sample twice; both runs must match each other and the goldens.

Goldens in ingestion/edi/tests/golden/: <name>.jsonl.sha256 per sample ("<sha256>  <lines>\\n"),
plus one readable <smallest>.first_st.jsonl (the first ST..SE set with its envelope headers).
`--update` rewrites them. Exit 1 names every mismatching file.
"""

from __future__ import annotations

import argparse
import hashlib
import sys
from pathlib import Path

from ingestion.edi.preparse import preparse

ROOT = Path(__file__).resolve().parents[2]
SAMPLES = ROOT / "datagen" / "samples"
GOLDEN = Path(__file__).resolve().parent / "tests" / "golden"
EXTS = (".834", ".835", ".837")


def samples() -> list[Path]:
    return sorted(p for p in SAMPLES.rglob("*") if p.is_file() and p.suffix in EXTS)


def digest(body: bytes) -> str:
    return f"{hashlib.sha256(body).hexdigest()}  {body.count(b'\n')}\n"


def first_st(body: bytes) -> bytes:
    """Lines up to and including the first SE (the envelope headers plus the first transaction set)."""
    out = []
    for line in body.splitlines(keepends=True):
        out.append(line)
        if b'"segment_id":"SE"' in line:
            break
    return b"".join(out)


def expected(files: list[Path]) -> dict[Path, bytes]:
    exp: dict[Path, bytes] = {}
    for f in files:
        a, b = preparse(f.read_bytes(), f.name), preparse(f.read_bytes(), f.name)
        if a != b:
            raise SystemExit(f"non-deterministic pre-parse: {f.name}")
        exp[GOLDEN / f"{f.name}.jsonl.sha256"] = digest(a).encode()
    if files:
        small = min(files, key=lambda p: (p.stat().st_size, p.name))
        exp[GOLDEN / f"{small.name}.first_st.jsonl"] = first_st(preparse(small.read_bytes(), small.name))
    return exp


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="python -m ingestion.edi.check")
    p.add_argument("--update", action="store_true")
    args = p.parse_args(argv)
    exp = expected(samples())
    if args.update:
        GOLDEN.mkdir(parents=True, exist_ok=True)
        for old in GOLDEN.iterdir():
            if old not in exp and old.is_file():
                old.unlink()
        for path, body in exp.items():
            path.write_bytes(body)
        print(f"edi-preparse-check: wrote {len(exp)} goldens")
        return 0
    bad = [p.name for p, body in exp.items() if not p.is_file() or p.read_bytes() != body]
    extra = sorted(p.name for p in GOLDEN.iterdir() if p.is_file() and p not in exp) if GOLDEN.is_dir() else []
    for name in bad:
        print(f"edi-preparse-check: MISMATCH {name}", file=sys.stderr)
    for name in extra:
        print(f"edi-preparse-check: STALE {name}", file=sys.stderr)
    if bad or extra:
        return 1
    print(f"edi-preparse-check: {len(exp)} goldens match")
    return 0


if __name__ == "__main__":
    sys.exit(main())
