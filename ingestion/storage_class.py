"""Storage-class reconciler (story 7): python -m ingestion.storage_class --profile demo

Lists landing objects with their storage class in one `gcloud storage ls --json` call, joins them by
object_uri to the latest ops.file_lifecycle row per object, and appends one row per object whose class
changed: the latest `state` repeated unchanged, `storage_class` = observed class, and detail
{"storage_class_from": prev|null, "storage_class_to": new}. Objects with no lifecycle row are skipped
(discovery owns `landed`). An unchanged rerun appends nothing. Logs never carry row values.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

import yaml

from ingestion import lifecycle
from ingestion.discover import URI_RE

RESOLVED = Path(__file__).resolve().parent.parent / "config" / "resolved.yaml"
CHUNK = 200  # rows per INSERT, keeps the bq parameter list bounded


def log(event: str, **fields) -> None:
    print(json.dumps({"event": event, **fields}, sort_keys=True, default=str), file=sys.stderr, flush=True)


def list_classes(bucket: str, run=subprocess.run) -> dict[str, str]:
    """{object_uri: storageClass} for AD-3 landing objects (generation suffix stripped)."""
    res = run(["gcloud", "storage", "ls", "--json", f"gs://{bucket}/**"], check=True, capture_output=True, text=True)
    items = json.loads(res.stdout) if res.stdout.strip() else []
    out = {}
    for it in items:
        uri = it.get("url", "").split("#", 1)[0]
        sc = (it.get("metadata") or {}).get("storageClass")
        if sc and URI_RE.match(uri):
            out[uri] = sc
    return out


def latest_rows(*, project_id: str, max_bytes_billed: int, uris: list[str], run=subprocess.run) -> dict[str, dict]:
    """{object_uri: {file_sha256, source, feed, state, storage_class}} from the latest row per object."""
    found: dict[str, dict] = {}
    for i in range(0, len(uris), CHUNK):
        part = uris[i : i + CHUNK]
        # latest state, but the last non-empty storage_class: loader rows carry no class
        sql = (f"SELECT object_uri, file_sha256, source, feed, state, "
               "LAST_VALUE(NULLIF(storage_class, '') IGNORE NULLS) OVER w AS storage_class "
               f"FROM `{project_id}.ops.file_lifecycle` WHERE object_uri IN UNNEST(@uris) "
               "QUALIFY ROW_NUMBER() OVER (PARTITION BY object_uri ORDER BY recorded_at DESC) = 1 "
               "WINDOW w AS (PARTITION BY object_uri ORDER BY recorded_at "
               "ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING)")  # fmt: skip
        args = [*lifecycle.bq_query_args(project_id, max_bytes_billed), "--format=json",
                f"--parameter=uris:ARRAY<STRING>:{json.dumps(part)}", sql]  # fmt: skip
        out = run(args, check=True, capture_output=True, text=True).stdout
        for r in json.loads(out) if out.lstrip().startswith("[") else []:
            found[r["object_uri"]] = r
    return found


def plan(observed: dict[str, str], latest: dict[str, dict]) -> list[dict]:
    """One move per object with a lifecycle row whose latest storage_class differs from the observed one."""
    moves = []
    for uri in sorted(observed):
        row = latest.get(uri)
        if row is None or row.get("storage_class") == observed[uri]:
            continue
        moves.append({**row, "object_uri": uri, "from": row.get("storage_class"), "to": observed[uri]})
    return moves


def append(*, project_id: str, max_bytes_billed: int, run_id: str, moves: list[dict], run=subprocess.run) -> int:
    """Insert moves in chunks of CHUNK rows; returns rows appended."""
    sql = (
        f"INSERT INTO `{project_id}.ops.file_lifecycle` "
        "(file_sha256, object_uri, source, feed, state, run_id, recorded_at, storage_class, detail) "
        "SELECT m.sha, m.uri, m.source, m.feed, m.state, @run, CURRENT_TIMESTAMP(), m.sc, "
        "PARSE_JSON(m.detail) FROM UNNEST(@rows) AS m"
    )
    types = "ARRAY<STRUCT<sha STRING, uri STRING, source STRING, feed STRING, state STRING, sc STRING, detail STRING>>"
    n = 0
    for i in range(0, len(moves), CHUNK):
        rows = [{"sha": m["file_sha256"], "uri": m["object_uri"], "source": m["source"], "feed": m["feed"],
                 "state": m["state"], "sc": m["to"],
                 "detail": json.dumps({"storage_class_from": m["from"], "storage_class_to": m["to"]}, sort_keys=True)}
                for m in moves[i : i + CHUNK]]  # fmt: skip
        args = [*lifecycle.bq_query_args(project_id, max_bytes_billed), f"--parameter=run:STRING:{run_id}",
                f"--parameter=rows:{types}:{json.dumps(rows)}", sql]  # fmt: skip
        run(args, check=True, capture_output=True, text=True)
        n += len(rows)
    return n


def reconcile(*, project_id: str, max_bytes_billed: int, bucket: str, run_id: str, run=subprocess.run) -> int:
    observed = list_classes(bucket, run)
    latest = latest_rows(project_id=project_id, max_bytes_billed=max_bytes_billed, uris=sorted(observed), run=run)
    moves = plan(observed, latest)
    n = append(project_id=project_id, max_bytes_billed=max_bytes_billed, run_id=run_id, moves=moves, run=run)
    log("storage_class_reconciled", run_id=run_id, objects=len(observed), tracked=len(latest),
        skipped_untracked=len(observed) - len(latest), rows_appended=n)  # fmt: skip
    return n


def main(argv: list[str] | None = None) -> int:
    from pipeline import runner

    parser = argparse.ArgumentParser(prog="python -m ingestion.storage_class")
    parser.add_argument("--profile", required=True)
    parser.parse_args(argv)
    cfg = yaml.safe_load(RESOLVED.read_text())
    project = cfg["project_id"]
    reconcile(project_id=project, max_bytes_billed=cfg["cost"]["max_bytes_billed"], bucket=f"{project}-landing",
              run_id=runner.mint_run_id(datetime.now(UTC)))  # fmt: skip
    return 0


if __name__ == "__main__":
    sys.exit(main())
