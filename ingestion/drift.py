"""ops.drift_report writes (AD-2/AD-5) via the bq CLI: one row per additive or unmapped era routing."""

from __future__ import annotations

import json
import subprocess

from ingestion.lifecycle import Runner, bq_query_args

MODE = "report_only"
KINDS = {"additive": "additive_columns", "unmapped": "unmapped_era"}


def record(
    *,
    project_id: str,
    max_bytes_billed: int,
    run_id: str,
    source: str,
    feed: str,
    schema_era: str,
    drift_kind: str,
    detail: dict,
    run: Runner = subprocess.run,
) -> None:
    """Header names and fingerprints only in `detail`; row values never leave Bronze."""
    params = {"run": run_id, "source": source, "feed": feed, "era": schema_era, "kind": drift_kind,
              "detail": json.dumps(detail, sort_keys=True), "mode": MODE}  # fmt: skip
    sql = (
        f"INSERT INTO `{project_id}.ops.drift_report` "
        "(run_id, source, feed, schema_era, drift_kind, detail, mode, reported_at) "
        "VALUES (@run, @source, @feed, @era, @kind, PARSE_JSON(@detail), @mode, CURRENT_TIMESTAMP())"
    )
    args = bq_query_args(project_id, max_bytes_billed) + [f"--parameter={k}:STRING:{v}" for k, v in params.items()]
    run([*args, sql], check=True, capture_output=True, text=True)
