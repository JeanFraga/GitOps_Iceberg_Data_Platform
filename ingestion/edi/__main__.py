"""python -m ingestion.edi <file> [--out DIR | --landing --source S --feed F]

Local mode writes <DIR>/<name>.jsonl (default: current directory). Landing mode reads a gs:// object
read-only and writes exactly one object to
gs://<project>-warehouse/edi_preparse/source=<source>/feed=<feed>/sha256=<sha>/<name>.jsonl
(project from config/resolved.yaml). Never writes to the raw file or the landing bucket.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

import yaml

from ingestion.edi.preparse import preparse

RESOLVED = Path(__file__).resolve().parents[2] / "config" / "resolved.yaml"


def log(event: str, **fields) -> None:
    print(json.dumps({"event": event, **fields}, sort_keys=True), file=sys.stderr, flush=True)


def landing_uri(project: str, source: str, feed: str, sha: str, name: str) -> str:
    return f"gs://{project}-warehouse/edi_preparse/source={source}/feed={feed}/sha256={sha}/{name}.jsonl"


def read_input(src: str, run=subprocess.run) -> bytes:
    if src.startswith("gs://"):
        return run(["gcloud", "storage", "cat", src], check=True, capture_output=True).stdout
    return Path(src).read_bytes()


class GcloudError(Exception):
    def __init__(self, returncode: int):
        super().__init__(f"gcloud exited {returncode}")
        self.returncode = returncode


def write_landing(uri: str, body: bytes, run=subprocess.run) -> str:
    """Upload once (if-generation-match=0). Existing object: equal bytes -> "exists", else "conflict"; never overwrites."""
    res = run(["gcloud", "storage", "cp", "--if-generation-match=0", "-", uri], input=body, capture_output=True)
    if res.returncode == 0:
        return "written"
    if b"Precondition" not in res.stderr and b"412" not in res.stderr:
        raise GcloudError(res.returncode)
    cur = run(["gcloud", "storage", "cat", uri], capture_output=True)
    if cur.returncode != 0:
        raise GcloudError(cur.returncode)
    return "exists" if cur.stdout == body else "conflict"


def main(argv: list[str] | None = None, run=subprocess.run) -> int:
    p = argparse.ArgumentParser(prog="python -m ingestion.edi")
    p.add_argument("file")
    mode = p.add_mutually_exclusive_group()
    mode.add_argument("--out", default=".")
    mode.add_argument("--landing", action="store_true")
    p.add_argument("--source")
    p.add_argument("--feed")
    args = p.parse_args(argv)
    if args.landing and not (args.source and args.feed):
        p.error("--landing needs --source and --feed")
    if not args.landing and (args.source or args.feed):
        p.error("--source/--feed are only valid with --landing")
    name = args.file.rstrip("/").rsplit("/", 1)[-1]
    try:
        data = read_input(args.file, run)
        body = preparse(data, name)
    except subprocess.CalledProcessError as e:
        log("edi_preparse_failed", file=name, error="CalledProcessError", gcloud_returncode=e.returncode)
        return 1
    except (ValueError, OSError) as e:
        log("edi_preparse_failed", file=name, error=type(e).__name__)
        return 1
    if args.landing:
        try:
            project = yaml.safe_load(RESOLVED.read_text())["project_id"]
        except (OSError, yaml.YAMLError, KeyError, TypeError) as e:
            log("edi_preparse_failed", file=name, error=type(e).__name__)
            return 1
        uri = landing_uri(project, args.source, args.feed, hashlib.sha256(data).hexdigest(), name)
        try:
            status = write_landing(uri, body, run)
        except GcloudError as e:
            log("edi_preparse_failed", file=name, uri=uri, gcloud_returncode=e.returncode)
            return 1
        log("edi_preparse_" + status, uri=uri, lines=body.count(b"\n"))
        if status == "conflict":
            return 1
    else:
        out = Path(args.out) / f"{name}.jsonl"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(body)
        log("edi_preparse_written", path=out.name, lines=body.count(b"\n"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
