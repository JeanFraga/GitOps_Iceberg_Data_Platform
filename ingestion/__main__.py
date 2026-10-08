"""Tracer Bronze load: python -m ingestion --profile demo --file gs://.../payer_b_members_2024.csv

Refuses an unmarked object (NFR-4), drops the CSV marker line, appends all-STRING rows plus
lineage to bronze_<source>.<feed>__<era> through AD-4 write-audit-publish. The era comes from the
AD-5 registry by fingerprint (ingestion/eras.py): known, additive (schema widened) or unmapped_<fp8>;
additive and unmapped routings write one ops.drift_report row after `reconciled`. Steps: skip a file already
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

from config.fingerprint import LAYOUTS, fingerprint, fp8
from ingestion import bronze, discover, drift, eras, land, lifecycle, reconcile
from ingestion.discover import URI_RE
from ingestion.marker import UnmarkedFile, check_marker, drop_marker_line
from ingestion.records import split
from pipeline import runner

RESOLVED = Path(__file__).resolve().parent.parent / "config" / "resolved.yaml"


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


def report_drift(project: str, cap: int, run_id: str, source: str, feed: str, route: eras.Route, detail: dict,
                 sha: str) -> None:  # fmt: skip
    """One ops.drift_report row for an additive or unmapped routing; written only after `reconciled`."""
    if route.kind == eras.KNOWN:
        return
    kind = drift.KINDS[route.kind]
    info = {"file_sha256": sha, "fingerprint": detail["fingerprint"], "fp8": detail["fp8"], "table": detail["table"]}
    if route.added:
        info["added_columns"] = route.added
    drift.record(project_id=project, max_bytes_billed=cap, run_id=run_id, source=source, feed=feed,
                 schema_era=route.era, drift_kind=kind, detail=info)  # fmt: skip
    log("drift_reported", run_id=run_id, drift_kind=kind, schema_era=route.era, **info)


class UnsupportedFormat(Exception):
    """The landed object's extension maps to no records.yaml format."""


FORMATS = {".csv": "csv", ".ndjson": "jsonl", ".jsonl": "jsonl", ".834": "x12", ".835": "x12", ".837": "x12"}


def format_of(uri: str) -> str | None:
    """records.yaml format from the object's extension, or None when unknown."""
    name = uri.rsplit("/", 1)[-1].lower()
    return next((fmt for ext, fmt in FORMATS.items() if name.endswith(ext)), None)


class ReconcileFail(Exception):
    """The WAP branch does not match the landed object; main was left untouched."""


def load(cfg: dict, uri: str, run_id: str, table_suffix: str = "") -> dict:
    m = URI_RE.match(uri)
    if not m:
        raise ValueError("FILE must be a landed gs:// URI: source=/feed=/ingest_date=/sha256=/<name>")
    if table_suffix and not re.fullmatch(r"_[a-z0-9_]+", table_suffix):
        raise ValueError("table suffix must match _[a-z0-9_]+")
    source, feed, path_sha = m["source"], m["feed"], m["sha"]
    fmt = format_of(uri)
    if fmt is None:
        log("refused_unsupported_format", object_uri=uri, run_id=run_id)
        raise UnsupportedFormat("extension maps to no known format (csv, ndjson/jsonl, 834/835/837)")
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

    # AD-3 duplicate: the same bytes already have lifecycle rows under another object_uri.
    # This object goes landed -> rejected_duplicate (terminal); the original keeps its own state.
    if lifecycle.sha_seen_elsewhere(project_id=project, max_bytes_billed=cap, file_sha256=sha, object_uri=uri):
        own = lifecycle.rows_for_uris(project_id=project, max_bytes_billed=cap, uris=[uri]).get(uri, [])
        if not any(r["state"] == "rejected_duplicate" for r in own):
            dup = {"project_id": project, "max_bytes_billed": cap, "file_sha256": sha, "object_uri": uri,
                   "source": source, "feed": feed, "run_id": run_id, "storage_class": None}  # fmt: skip
            if not own:
                lifecycle.record(**dup, state="landed", detail={"bytes": len(data)})
                log("landed", object_uri=uri, file_sha256=sha, run_id=run_id)
            lifecycle.record(**dup, state="rejected_duplicate", detail={"reason": "sha256_landed_under_other_uri"})
        log("rejected_duplicate", object_uri=uri, file_sha256=sha, run_id=run_id)
        return {"run_id": run_id, "skipped": "rejected_duplicate", "object_uri": uri}

    # AD-5: route on the layout fingerprint, never on dates or names. CSV: the header (marker line
    # dropped); jsonl/x12: the whole file (their markers sit inside records and are kept).
    records = split(data, fmt)
    if fmt == "csv":
        records = drop_marker_line(records)
        text = "\n".join(r.raw.decode("utf-8", errors="replace") for r in records[:1])
    else:
        # Only records that decode as UTF-8: a bad byte would become U+FFFD and break jsonl_layout's JSON
        # parse; that record still loads (base64 in _raw_line).
        text = "\n".join(r.raw.decode("utf-8") for r in records if r.encoding == "utf-8")
    fp = fingerprint(text, fmt)
    route = eras.resolve(source, feed, fp, LAYOUTS[fmt](text))
    namespace, table = f"bronze_{source}", f"{feed}__{route.era}{table_suffix}"
    qualified = f"{namespace}.{table}"

    # Idempotent reload: skip a file whose append to this table finished -- reconciled or
    # quarantined (replay is E4's job), or a pre-WAP (3.1) append with no branch. A WAP attempt
    # that died between bronze_appended and the gate outcome is retried on a replaced branch.
    seen = lifecycle.latest_states(project_id=project, max_bytes_billed=cap, file_sha256=sha)
    # Checked across every era table of this feed (same demo suffix): after an AD-5 registry
    # rebind the file routes to a new era, but it must not be appended a second time.
    mine = [s for s in seen if s["table"] == qualified]
    done = [s for s in seen if (s["table"] or "").startswith(f"{namespace}.{feed}__")
            and (s["table"] or "").endswith(table_suffix)]  # fmt: skip
    if any(s["state"] in ("reconciled", "quarantined") for s in done) or any(
        s["state"] == "bronze_appended" and not s.get("branch") for s in done
    ):
        log("skipped_already_appended", object_uri=uri, file_sha256=sha, run_id=run_id, table=qualified)
        return {"run_id": run_id, "skipped": "already_appended", "table": qualified}

    storage_class = json.loads(_gcloud(["objects", "describe", uri, "--format=json"])).get("storage_class")
    common = {"project_id": project, "max_bytes_billed": cap, "file_sha256": sha, "object_uri": uri,
              "source": source, "feed": feed, "run_id": run_id, "storage_class": storage_class}  # fmt: skip
    if not any(s["state"] == "landed" for s in seen):
        lifecycle.record(**common, state="landed", detail={"bytes": len(data)})
        log("landed", object_uri=uri, file_sha256=sha, run_id=run_id)

    columns, rows = bronze.build_rows(
        records, fmt, ingested_at=datetime.now(UTC), source_file=uri, record_source=f"{source}.{feed}", sha256=sha,
        run_id=run_id,
    )  # fmt: skip
    detail = {"rows": len(rows), "era": route.era, "era_kind": route.kind, "fingerprint": fp, "fp8": fp8(fp), "table": qualified,
              "ragged_rows": bronze.ragged_count(records, fmt)}  # fmt: skip
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
            report_drift(project, cap, run_id, source, feed, route, detail, sha)
            return {"run_id": run_id, **detail, "skipped": "already_published"}
        ident, branch = bronze.write_branch(spark, namespace, table, columns, rows, run_id, sha)
        detail["branch"] = branch
        if not any(s["state"] == "bronze_appended" for s in mine):  # lifecycle.yaml: no self-transition
            lifecycle.record(**common, state="bronze_appended", detail=detail)
        log("bronze_appended", object_uri=uri, file_sha256=sha, run_id=run_id, **detail)

        # AD-4 audit: count + per-record SHA-256 against the landed bytes.
        result = reconcile.gate(bronze.data_records(records, fmt), bronze.branch_rows(spark, ident, branch, run_id))
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
    report_drift(project, cap, run_id, source, feed, route, detail, sha)

    read = bq_count(project, cap, table_ref, run_id)
    log("bigquery_read", table_ref=table_ref, run_id=run_id, **read)
    if read["rows"] != len(rows):
        raise RuntimeError(f"BigQuery read {read['rows']} rows, published {len(rows)}")
    return {"run_id": run_id, **detail, "bigquery": read}


EXIT_CODES = ((UnmarkedFile, 3), (UnsupportedFormat, 5), (ReconcileFail, 4))


def exit_code(exc: BaseException) -> int:
    """Type-only error line; exception text can carry row values."""
    for kind, code in EXIT_CODES:
        if isinstance(exc, kind):
            msg = {3: "no synthetic marker; file refused", 5: "unsupported file format; file refused",
                   4: "reconcile gate failed; file quarantined, main untouched"}[code]  # fmt: skip
            log("error", error_type=kind.__name__, error=msg)
            return code
    if isinstance(exc, subprocess.CalledProcessError):
        log("error", error_type="CalledProcessError", error="external command failed", returncode=exc.returncode)
        return 1
    log("error", error_type=type(exc).__name__, error="load failed")
    return 1


def record_refused_landed(cfg: dict, uri: str, run_id: str) -> None:
    """Batch: an unmarked object with no lifecycle row gets one `landed` row carrying the refusal.

    lifecycle.yaml has no refused state; discovery skips a `landed` row with detail.refused, so a rerun
    does not refuse (and fail) the same object again."""
    m = URI_RE.match(uri)
    lifecycle.record(project_id=cfg["project_id"], max_bytes_billed=cfg["cost"]["max_bytes_billed"],
                     file_sha256=m["sha"], object_uri=uri, source=m["source"], feed=m["feed"], state="landed",
                     run_id=run_id, storage_class=None, detail={"discovered": True, "refused": "unmarked"})  # fmt: skip
    log("landed", object_uri=uri, file_sha256=m["sha"], run_id=run_id, discovered=True, refused="unmarked")


def run_batch(cfg: dict, run_id: str, table_suffix: str = "") -> dict:
    """Load every pending landing object; one failure never stops the others."""
    project, cap = cfg["project_id"], cfg["cost"]["max_bytes_billed"]
    todo = discover.pending(project, cap, f"{project}-landing")
    log("discovered", run_id=run_id, pending=len(todo))
    summary: dict = {"loaded": [], "skipped": [], "failed": {}}
    for uri, has_rows in todo:
        if format_of(uri) is None:
            log("skipped_unsupported_format", object_uri=uri, run_id=run_id)
            summary["skipped"].append(uri)
            continue
        # One run_id per file: the reconcile gate reads branch rows by _run_id, so files sharing a run_id
        # in one table would be counted together. The batch lock stays held under the batch run_id.
        file_run = runner.mint_run_id(datetime.now(UTC))
        try:
            try:
                out = load(cfg, uri, file_run, table_suffix)
            except UnmarkedFile:
                if not has_rows:
                    record_refused_landed(cfg, uri, file_run)
                raise
            (summary["skipped"] if out.get("skipped") else summary["loaded"]).append(uri)
        except Exception as exc:  # noqa: BLE001 - per-file isolation; logged type-only
            log("file_failed", object_uri=uri, run_id=file_run, batch_run_id=run_id)
            summary["failed"][uri] = exit_code(exc)
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", required=True)
    parser.add_argument("--file", default="", help="one landed gs:// URI; empty runs batch discovery")
    parser.add_argument("--land", default="", metavar="SRC", help="land SRC/<source>/<feed>/<file> under AD-3")
    parser.add_argument("--table-suffix", default="", help="demo only: load into <feed>__<era><suffix>")
    args = parser.parse_args(argv)
    cfg = yaml.safe_load(RESOLVED.read_text())
    if cfg["profile"] != args.profile:
        log("error", error=f"resolved.yaml is for profile {cfg['profile']}; run make resolve PROFILE={args.profile}")
        return 2
    if args.land:
        try:
            out = land.land_dir(Path(args.land), f"{cfg['project_id']}-landing", datetime.now(UTC).date().isoformat(),
                                log)  # fmt: skip
        except Exception as exc:  # noqa: BLE001 - type only
            log("error", error_type=type(exc).__name__, error="land failed")
            return 1
        log("land_done", landed=len(out["landed"]), rejected_overwrite=len(out["rejected_overwrite"]),
            failed=out["failed"])  # fmt: skip
        return 1 if out["failed"] else 0
    backend = runner.BigQueryBackend(cfg["project_id"], cfg["cost"]["max_bytes_billed"])
    result: dict = {}
    if not args.file:
        try:
            runner.run(backend, f"{cfg['profile']}:bronze", cfg["run"]["lock_ttl_minutes"],
                       task=lambda run_id: result.update(run_batch(cfg, run_id, args.table_suffix)))  # fmt: skip
        except Exception as exc:  # noqa: BLE001 - type only
            return exit_code(exc)
        failed = result["failed"]
        log("batch_done", loaded=len(result["loaded"]), skipped=len(result["skipped"]), failed=sorted(failed))
        codes = set(failed.values())
        return 0 if not codes else codes.pop() if len(codes) == 1 else 1
    try:
        runner.run(backend, f"{cfg['profile']}:bronze", cfg["run"]["lock_ttl_minutes"],
                   task=lambda run_id: result.update(load(cfg, args.file, run_id, args.table_suffix)))  # fmt: skip
    except Exception as exc:  # noqa: BLE001 - type only: exception text can carry row values
        return exit_code(exc)
    log("done", **result)
    return 0


if __name__ == "__main__":
    sys.exit(main())
