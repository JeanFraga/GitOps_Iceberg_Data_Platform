"""FR-35 PHI scan and synthetic-marker check (AD-14, NFR-4). Both exit 1 on any finding.

  python tools/guardrails.py phi-scan [PATH]      # default: every git-tracked file
  python tools/guardrails.py marker-check [PATH]  # default: every git-tracked data file (incl. datagen/samples/)
  python tools/guardrails.py repo-weight [PATH]   # FR-37: data files over the record or byte limit

Findings print the file and line (PHI) but never the matched value.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parent.parent
SPEC = yaml.safe_load((REPO / "config" / "standards" / "guardrails.yaml").read_text())


SAMPLES = "datagen/samples/"
X12_EXTENSIONS = (".x12", ".edi", ".834", ".835", ".837")
X12_RECORD_SEGMENTS = {"CLM", "CLP", "INS"}


def _repo_files(skip: list[str] | None = None) -> list[Path]:
    skip = SPEC["allowlist"] if skip is None else skip
    tracked = subprocess.run(["git", "ls-files", "-z"], cwd=REPO, check=True, capture_output=True).stdout
    names = [n for n in tracked.decode().split("\0") if n]
    kept = (REPO / n for n in names if not any(n.startswith(a) for a in skip))
    return [p for p in kept if p.is_file()]  # skip tracked files deleted in the working tree


def _files(path: str | None, skip: list[str] | None = None) -> list[Path]:
    if path is None:
        return _repo_files(skip)
    root = Path(path)
    if not root.exists():
        raise FileNotFoundError(f"no such path: {path}")
    return [root] if root.is_file() else sorted(p for p in root.rglob("*") if p.is_file())


def _is_data_file(p: Path) -> bool:
    return any(p.name.endswith(ext) for ext in SPEC["synthetic_marker"]["data_extensions"])


def phi_scan(path: str | None, extra_names: list[str] = ()) -> list[str]:
    cfg = SPEC["phi_scan"]
    patterns = {k: re.compile(v) for k, v in cfg["patterns"].items()}
    names = [n for n in [*cfg["names"], *extra_names] if n.strip()]
    if names:
        alternatives = "|".join(re.escape(n.strip()) for n in names)
        patterns["full_name"] = re.compile(rf"\b(?:{alternatives})\b", re.IGNORECASE)
    findings = []
    for f in _files(path):
        if f.stat().st_size > cfg["max_file_bytes"]:
            continue
        text = f.read_bytes().decode("utf-8", errors="replace")
        for lineno, line in enumerate(text.splitlines(), 1):
            findings += [f"{f}:{lineno}: {kind}" for kind, rx in patterns.items() if rx.search(line)]
    return findings


def marker_check(path: str | None) -> list[str]:
    cfg = SPEC["synthetic_marker"]
    token = cfg["token"].encode()
    findings = []
    for f in _files(path, [a for a in SPEC["allowlist"] if a != SAMPLES]):
        if not _is_data_file(f):
            continue
        with f.open("rb") as fh:
            if token not in fh.read(cfg["within_bytes"]):
                findings.append(f"{f}: missing synthetic marker")
    return findings


def _records(f: Path) -> int:
    text = f.read_bytes().decode("utf-8", errors="replace")
    if f.name.endswith(X12_EXTENSIONS):
        return sum(1 for seg in text.split("~") if seg.strip().split("*", 1)[0] in X12_RECORD_SEGMENTS)
    lines = [ln for ln in text.splitlines() if ln.strip() and not ln.startswith("#")]
    return max(len(lines) - (1 if f.name.endswith(".csv") else 0), 0)


def repo_weight(path: str | None) -> list[str]:
    """FR-37: data files outside datagen/samples/ above repo_weight.sample_records or max_bytes."""
    cfg = SPEC["repo_weight"]
    findings = []
    for f in _files(path, [*SPEC["allowlist"], SAMPLES]):
        if not _is_data_file(f) or SAMPLES in f.resolve().as_posix() + "/":
            continue
        size = f.stat().st_size
        if size > cfg["max_bytes"]:
            findings.append(f"{f}: bytes {size} > {cfg['max_bytes']}")
            continue
        records = _records(f)
        if records > cfg["sample_records"]:
            findings.append(f"{f}: records {records} > {cfg['sample_records']}")
    return findings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("check", choices=["phi-scan", "marker-check", "repo-weight"])
    parser.add_argument("path", nargs="?", help="file or directory; default is the repo minus the allowlist")
    parser.add_argument(
        "--names", action="extend", nargs=1, default=[], metavar="NAME", help="generated full name to flag; repeatable"
    )
    parser.add_argument("--names-file", metavar="PATH", help="file of generated full names, one per line")
    args = parser.parse_args(argv)
    if args.names_file:
        args.names += Path(args.names_file).read_text().splitlines()
    try:
        if args.check == "phi-scan":
            findings = phi_scan(args.path, args.names)
        elif args.check == "marker-check":
            findings = marker_check(args.path)
        else:
            findings = repo_weight(args.path)
    except FileNotFoundError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    for line in findings:
        print(line, file=sys.stderr)
    scope = args.path or "repo"
    print(f"{args.check}: {len(findings)} finding(s) in {scope}")
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())
