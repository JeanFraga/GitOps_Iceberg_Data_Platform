"""Tracer Bronze load: python -m ingestion --profile demo --file gs://.../payer_b_members_2024.csv

Refuses an unmarked object (NFR-4), drops the CSV marker line, appends all-STRING rows plus
lineage to bronze_<source>.<feed>__<era> through AD-4 write-audit-publish: skip a file already
appended, record `landed` once, write branch wap_<sha8> (`bronze_appended`), run the reconcile
gate, then fast-forward main (`reconciled`) or quarantine (`quarantined` + ops.quarantine
RECONCILE_FAIL), and prove a BigQuery read. Logs are JSON lines on
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
from ingestion import bronze, lifecycle, reconcile
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
    return {
        "rows": int(row["n"]),
        "min_ordinal": int(row["min_ordinal"]) if row.get("min_ordinal") is not None else None,
    }


class ReconcileFail(Exception):
    """The WAP branch does not match the landed object; main was left untouched."""


def load(cfg: dict, uri: str, run_id: str, table_suffix: str = "") -> dict:
    m = URI_RE.match(uri)
    if not m:
        raise ValueError("FILE must be a landed gs:// URI: source=/feed=/ingest_date=/sha256=/<name>")
    if table_suffix and not re.fullmatch(r"_[a-z0-9_]+", table_suffix):
        raise ValueError("table suffix must match _[a-z0-9_]+")
    source, feed, path_sha = m["source"], m["feed"], m["sha"]
    project, cap = cfg["project_id"], cfg["cost"]["max_bytes_billed"]
    namespace, table = f"bronze_{source}", f"{feed}__{FIXED_ERA}{table_suffix}"
    qualified = f"{namespace}.{table}"

    data = _gcloud(["cat", uri])
    sha = hashlib.sha256(data).hexdigest()
    if sha != path_sha:
        raise ValueError(f"object sha256 {sha} does not match its landed path")
    try:
        check_marker(data)
    except UnmarkedFile:
        log("refused_unmarked", object_uri=uri, file_sha256=sha, run_id=run_id)
        raise

    # Idempotent reload: skip a file whose append to this table finished -- reconciled or
    # quarantined (replay is E4's job), or a pre-WAP (3.1) append with no branch. A WAP attempt
    # that died between bronze_appended and the gate outcome is retried on a replaced branch.
    seen = lifecycle.latest_states(project_id=project, max_bytes_billed=cap, file_sha256=sha)
    mine = [s for s in seen if s["table"] == qualified]
    if any(s["state"] in ("reconciled", "quarantined") for s in mine) or any(
        s["state"] == "bronze_appended" and not s.get("branch") for s in mine
    ):
        log("skipped_already_appended", object_uri=uri, file_sha256=sha, run_id=run_id, table=qualified)
        return {"run_id": run_id, "skipped": "already_appended", "table": qualified}

    storage_class = json.loads(_gcloud(["objects", "describe", uri, "--format=json"])).get("storage_class")
    common = {"project_id": project, "max_bytes_billed": cap, "file_sha256": sha, "object_uri": uri,
              "source": source, "feed": feed, "run_id": run_id, "storage_class": storage_class}  # fmt: skip
    if not any(s["state"] == "landed" for s in seen):
        lifecycle.record(**common, state="landed", detail={"bytes": len(data)})
        log("landed", object_uri=uri, file_sha256=sha, run_id=run_id)

    records = drop_marker_line(split(data, "csv"))
    text = "\n".join(r.raw.decode("utf-8", errors="replace") for r in records[:1])
    fp = fingerprint(text, "csv")
    columns, rows = bronze.build_rows(
        records, ingested_at=datetime.now(UTC), source_file=uri, record_source=f"{source}.{feed}", sha256=sha,
        run_id=run_id,
    )  # fmt: skip
    detail = {"rows": len(rows), "era": FIXED_ERA, "fingerprint": fp, "fp8": fp8(fp), "table": qualified,
              "ragged_rows": bronze.ragged_count(records)}  # fmt: skip
    table_ref = f"{project}.{project}-warehouse.{namespace}.{table}"

    spark = bronze.build_session(bronze.rest_catalog_conf(project), cfg["versions"])
    try:
        # AD-4 write: this delivery goes to wap_<sha8>; main is untouched until the gate passes.
        # Recovery: a publish that landed on main but lost its `reconciled` row is not re-published.
        published = bronze.published_snapshot(spark, bronze.ensure_table(spark, namespace, table, columns), sha)
        if published is not None:
            detail.update(snapshot_id=published, recovered="published_without_reconciled")
            lifecycle.record(**common, state="reconciled", detail=detail)
            log("reconciled", object_uri=uri, file_sha256=sha, run_id=run_id, **detail)
            return {"run_id": run_id, **detail, "skipped": "already_published"}
        ident, branch = bronze.write_branch(spark, namespace, table, columns, rows, run_id, sha)
        detail["branch"] = branch
        if not any(s["state"] == "bronze_appended" for s in mine):  # lifecycle.yaml: no self-transition
            lifecycle.record(**common, state="bronze_appended", detail=detail)
        log("bronze_appended", object_uri=uri, file_sha256=sha, run_id=run_id, **detail)

        # AD-4 audit: count + per-record SHA-256 against the landed bytes.
        result = reconcile.gate(records[1:], bronze.branch_rows(spark, ident, branch, run_id))
        if not result.passed:
            qdetail = {**result.detail, "table": qualified, "branch": branch, "reason": reconcile.REASON}
            lifecycle.record(**common, state="quarantined", detail=qdetail)
            lifecycle.quarantine(project_id=project, max_bytes_billed=cap, file_sha256=sha,
                                 reason=reconcile.REASON, run_id=run_id,
                                 line_ordinal=result.first_mismatch_ordinal)  # fmt: skip
            log("quarantined", object_uri=uri, file_sha256=sha, run_id=run_id, **qdetail)
            raise ReconcileFail(reconcile.REASON)

        # The branch must stay invisible to BigQuery (it reads main only).
        pre = bq_count(project, cap, table_ref, run_id)
        log("bigquery_pre_publish", table_ref=table_ref, run_id=run_id, rows=pre["rows"])
        if pre["rows"] != 0:
            raise RuntimeError("BigQuery sees the WAP branch before publish")

        # AD-4 publish: fast-forward main to the branch (one new snapshot on main).
        detail["snapshot_id"] = bronze.publish(spark, ident, branch, run_id)
    finally:
        spark.stop()
    lifecycle.record(**common, state="reconciled", detail={**detail, "expected": result.expected,
                                                           "actual": result.actual})  # fmt: skip
    log("reconciled", object_uri=uri, file_sha256=sha, run_id=run_id, **detail)

    read = bq_count(project, cap, table_ref, run_id)
    log("bigquery_read", table_ref=table_ref, run_id=run_id, **read)
    if read["rows"] != len(rows):
        raise RuntimeError(f"BigQuery read {read['rows']} rows, published {len(rows)}")
    return {"run_id": run_id, **detail, "bigquery": read}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", required=True)
    parser.add_argument("--file", required=True)
    parser.add_argument("--table-suffix", default="", help="demo only: load into <feed>__<era><suffix>")
    args = parser.parse_args(argv)
    cfg = yaml.safe_load(RESOLVED.read_text())
    if cfg["profile"] != args.profile:
        log("error", error=f"resolved.yaml is for profile {cfg['profile']}; run make resolve PROFILE={args.profile}")
        return 2
    backend = runner.BigQueryBackend(cfg["project_id"], cfg["cost"]["max_bytes_billed"])
    result: dict = {}
    try:
        runner.run(backend, f"{cfg['profile']}:bronze", cfg["run"]["lock_ttl_minutes"],
                   task=lambda run_id: result.update(load(cfg, args.file, run_id, args.table_suffix)))  # fmt: skip
    except UnmarkedFile:
        log("error", error_type="UnmarkedFile", error="no synthetic marker; file refused")
        return 3
    except ReconcileFail:
        log("error", error_type="ReconcileFail", error="reconcile gate failed; file quarantined, main untouched")
        return 4
    except subprocess.CalledProcessError as exc:
        log("error", error_type="CalledProcessError", error="external command failed", returncode=exc.returncode)
        return 1
    except Exception as exc:  # noqa: BLE001 - type only: exception text can carry row values
        log("error", error_type=type(exc).__name__, error="load failed")
        return 1
    log("done", **result)
    return 0


if __name__ == "__main__":
    sys.exit(main())
