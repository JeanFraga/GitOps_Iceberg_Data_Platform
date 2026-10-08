"""Tracer Bronze load: python -m ingestion --profile demo --file gs://.../payer_b_members_2024.csv

Refuses an unmarked object (NFR-4), drops the CSV marker line, appends all-STRING rows plus
lineage to bronze_<source>.<feed>__<era> in the BigLake REST catalog, records `landed` and
`bronze_appended` in ops.file_lifecycle and proves a BigQuery read. Logs are JSON lines on
stderr and never carry row values.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

import yaml

from config.fingerprint import fingerprint, fp8
from ingestion import bronze, lifecycle
from ingestion.marker import UnmarkedFile, check_marker, drop_marker_line
from ingestion.records import split
from pipeline import runner

RESOLVED = Path(__file__).resolve().parent.parent / "config" / "resolved.yaml"
URI_RE = re.compile(r"^gs://[^/]+/source=(?P<source>[^/]+)/feed=(?P<feed>[^/]+)/.*?sha256=(?P<sha>[0-9a-f]{64})/[^/]+$")
FIXED_ERA = "era_2024"  # tracer: fingerprint routing is entry 3


def log(event: str, **fields) -> None:
    print(json.dumps({"event": event, **fields}, sort_keys=True, default=str), file=sys.stderr, flush=True)


def _gcloud(args: list[str]) -> bytes:
    return subprocess.run(["gcloud", "storage", *args], check=True, capture_output=True).stdout


def bq_count(project_id: str, cap: int, table_ref: str, run_id: str) -> dict:
    sql = (f"SELECT COUNT(*) AS n, MIN(_line_ordinal) AS min_ordinal FROM `{table_ref}` "
           "WHERE _run_id = @run")  # fmt: skip
    args = [*lifecycle.bq_query_args(project_id, cap), "--format=json", f"--parameter=run:STRING:{run_id}", sql]
    out = subprocess.run(args, check=True, capture_output=True, text=True).stdout
    row = json.loads(out)[0]
    return {"rows": int(row["n"]), "min_ordinal": int(row["min_ordinal"])}


def load(cfg: dict, uri: str, run_id: str) -> dict:
    m = URI_RE.match(uri)
    if not m:
        raise ValueError("FILE must be a landed gs:// URI: source=/feed=/ingest_date=/sha256=/<name>")
    source, feed, path_sha = m["source"], m["feed"], m["sha"]
    project, cap = cfg["project_id"], cfg["cost"]["max_bytes_billed"]

    data = _gcloud(["cat", uri])
    sha = hashlib.sha256(data).hexdigest()
    if sha != path_sha:
        raise ValueError(f"object sha256 {sha} does not match its landed path")
    try:
        check_marker(data)
    except UnmarkedFile:
        log("refused_unmarked", object_uri=uri, file_sha256=sha, run_id=run_id)
        raise
    storage_class = json.loads(_gcloud(["objects", "describe", uri, "--format=json"])).get("storage_class")
    common = {"project_id": project, "max_bytes_billed": cap, "file_sha256": sha, "object_uri": uri,
              "source": source, "feed": feed, "run_id": run_id, "storage_class": storage_class}  # fmt: skip
    lifecycle.record(**common, state="landed", detail={"bytes": len(data)})
    log("landed", object_uri=uri, file_sha256=sha, run_id=run_id)

    records = drop_marker_line(split(data, "csv"))
    text = "\n".join(r.raw.decode("utf-8", errors="replace") for r in records[:1])
    fp = fingerprint(text, "csv")
    namespace, table = f"bronze_{source}", f"{feed}__{FIXED_ERA}"
    columns, rows = bronze.build_rows(
        records, ingested_at=datetime.now(UTC), source_file=uri, record_source=f"{source}.{feed}", sha256=sha,
        run_id=run_id,
    )  # fmt: skip
    spark = bronze.build_session(bronze.rest_catalog_conf(project), cfg["versions"])
    try:
        snapshot_id = bronze.append(spark, namespace, table, columns, rows, run_id)
    finally:
        spark.stop()
    detail = {"rows": len(rows), "era": FIXED_ERA, "fingerprint": fp, "fp8": fp8(fp),
              "table": f"{namespace}.{table}", "snapshot_id": snapshot_id}  # fmt: skip
    lifecycle.record(**common, state="bronze_appended", detail=detail)
    log("bronze_appended", object_uri=uri, file_sha256=sha, run_id=run_id, **detail)

    table_ref = f"{project}.{project}-warehouse.{namespace}.{table}"
    read = bq_count(project, cap, table_ref, run_id)
    log("bigquery_read", table_ref=table_ref, run_id=run_id, **read)
    if read["rows"] != len(rows):
        raise RuntimeError(f"BigQuery read {read['rows']} rows, appended {len(rows)}")
    return {"run_id": run_id, **detail, "bigquery": read}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", required=True)
    parser.add_argument("--file", required=True)
    args = parser.parse_args(argv)
    cfg = yaml.safe_load(RESOLVED.read_text())
    if cfg["profile"] != args.profile:
        log("error", error=f"resolved.yaml is for profile {cfg['profile']}; run make resolve PROFILE={args.profile}")
        return 2
    backend = runner.BigQueryBackend(cfg["project_id"], cfg["cost"]["max_bytes_billed"])
    result: dict = {}
    try:
        runner.run(backend, f"{cfg['profile']}:bronze", cfg["run"]["lock_ttl_minutes"],
                   task=lambda run_id: result.update(load(cfg, args.file, run_id)))  # fmt: skip
    except UnmarkedFile as exc:
        log("error", error_type="UnmarkedFile", error=str(exc))
        return 3
    except subprocess.CalledProcessError as exc:
        log(
            "error",
            error_type="CalledProcessError",
            cmd=exc.cmd[:3],
            returncode=exc.returncode,
            stderr=(exc.stderr or b"")[-400:]
            if isinstance(exc.stderr, str)
            else (exc.stderr or b"")[-400:].decode(errors="replace"),
        )
        return 1
    except Exception as exc:  # noqa: BLE001 - one structured line, no row values
        log("error", error_type=type(exc).__name__, error=str(exc)[:500])
        return 1
    log("done", **result)
    return 0


if __name__ == "__main__":
    sys.exit(main())
