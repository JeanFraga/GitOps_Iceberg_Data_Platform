"""FR-35 PHI scan and synthetic-marker check (AD-14, NFR-4). Both exit 1 on any finding.

  python tools/guardrails.py phi-scan [PATH]      # default: every git-tracked file
  python tools/guardrails.py marker-check [PATH]  # default: every git-tracked data file

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


def _repo_files() -> list[Path]:
    tracked = subprocess.run(["git", "ls-files", "-z"], cwd=REPO, check=True, capture_output=True).stdout
    names = [n for n in tracked.decode().split("\0") if n]
    kept = (REPO / n for n in names if not any(n.startswith(a) for a in SPEC["allowlist"]))
    return [p for p in kept if p.is_file()]  # skip tracked files deleted in the working tree


def _files(path: str | None) -> list[Path]:
    if path is None:
        return _repo_files()
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
    for f in _files(path):
        if not _is_data_file(f):
            continue
        with f.open("rb") as fh:
            if token not in fh.read(cfg["within_bytes"]):
                findings.append(f"{f}: missing synthetic marker")
    return findings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("check", choices=["phi-scan", "marker-check"])
    parser.add_argument("path", nargs="?", help="file or directory; default is the repo minus the allowlist")
    parser.add_argument(
        "--names", action="extend", nargs=1, default=[], metavar="NAME", help="generated full name to flag; repeatable"
    )
    args = parser.parse_args(argv)
    try:
        findings = phi_scan(args.path, args.names) if args.check == "phi-scan" else marker_check(args.path)
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
