"""ops.file_lifecycle writes (AD-4/AD-10) via the bq CLI. States come from lifecycle.yaml."""

from __future__ import annotations

import json
import subprocess
from collections.abc import Callable
from pathlib import Path

import yaml

LIFECYCLE = Path(__file__).resolve().parent.parent / "config" / "standards" / "lifecycle.yaml"
Runner = Callable[..., subprocess.CompletedProcess]


def states() -> list[str]:
    return yaml.safe_load(LIFECYCLE.read_text())["states"]


def bq_query_args(project_id: str, max_bytes_billed: int) -> list[str]:
    return ["bq", f"--project_id={project_id}", "query", "--use_legacy_sql=false", "--quiet",
            f"--maximum_bytes_billed={max_bytes_billed}"]  # fmt: skip


def record(
    *,
    project_id: str,
    max_bytes_billed: int,
    file_sha256: str,
    object_uri: str,
    source: str,
    feed: str,
    state: str,
    run_id: str,
    storage_class: str | None,
    detail: dict,
    run: Runner = subprocess.run,
) -> None:
    if state not in states():
        raise ValueError(f"unknown lifecycle state: {state}")
    params = {
        "sha": file_sha256, "uri": object_uri, "source": source, "feed": feed, "state": state,
        "run": run_id, "sc": storage_class or "", "detail": json.dumps(detail, sort_keys=True),
    }  # fmt: skip
    sql = (
        f"INSERT INTO `{project_id}.ops.file_lifecycle` "
        "(file_sha256, object_uri, source, feed, state, run_id, recorded_at, storage_class, detail) "
        "VALUES (@sha, @uri, @source, @feed, @state, @run, CURRENT_TIMESTAMP(), NULLIF(@sc, ''), PARSE_JSON(@detail))"
    )
    args = bq_query_args(project_id, max_bytes_billed) + [f"--parameter={k}:STRING:{v}" for k, v in params.items()]
    run([*args, sql], check=True, capture_output=True, text=True)


def latest_states(
    *, project_id: str, max_bytes_billed: int, file_sha256: str, run: Runner = subprocess.run
) -> list[dict]:
    """[{state, table, branch}] recorded for one file, oldest first. `table` is detail.table (Bronze states only)."""
    sql = (f"SELECT state, JSON_VALUE(detail, '$.table') AS table, "
           f"JSON_VALUE(detail, '$.branch') AS branch FROM `{project_id}.ops.file_lifecycle` "
           "WHERE file_sha256 = @sha ORDER BY recorded_at")  # fmt: skip
    args = [*bq_query_args(project_id, max_bytes_billed), "--format=json", f"--parameter=sha:STRING:{file_sha256}"]
    out = run([*args, sql], check=True, capture_output=True, text=True).stdout
    rows = json.loads(out) if out.lstrip().startswith("[") else []
    return [{"state": r["state"], "table": r.get("table"), "branch": r.get("branch")} for r in rows]


def quarantine(
    *,
    project_id: str,
    max_bytes_billed: int,
    file_sha256: str,
    reason: str,
    run_id: str,
    line_ordinal: int | None = None,
    run: Runner = subprocess.run,
) -> None:
    """One ops.quarantine row. raw_line stays NULL: row values never leave Bronze."""
    params = [f"--parameter=sha:STRING:{file_sha256}", f"--parameter=reason:STRING:{reason}",
              f"--parameter=run:STRING:{run_id}"]  # fmt: skip
    if line_ordinal is not None:
        params.append(f"--parameter=ord:INT64:{int(line_ordinal)}")
    sql = (
        f"INSERT INTO `{project_id}.ops.quarantine` "
        "(file_sha256, line_ordinal, reason, raw_line, run_id, quarantined_at) "
        f"VALUES (@sha, {'@ord' if line_ordinal is not None else 'NULL'}, @reason, NULL, @run, CURRENT_TIMESTAMP())"
    )
    run([*bq_query_args(project_id, max_bytes_billed), *params, sql], check=True, capture_output=True, text=True)


def rows_for_uris(
    *, project_id: str, max_bytes_billed: int, uris: list[str], run: Runner = subprocess.run
) -> dict[str, list[dict]]:
    """{object_uri: [{state, refused}, ...] oldest first} for the given landing URIs (discovery join)."""
    if not uris:
        return {}
    sql = (f"SELECT object_uri, state, JSON_VALUE(detail, '$.refused') AS refused "
           f"FROM `{project_id}.ops.file_lifecycle` "
           "WHERE object_uri IN UNNEST(@uris) ORDER BY recorded_at")  # fmt: skip
    param = f"--parameter=uris:ARRAY<STRING>:{json.dumps(uris)}"
    out = run([*bq_query_args(project_id, max_bytes_billed), "--format=json", param, sql],
              check=True, capture_output=True, text=True).stdout  # fmt: skip
    rows = json.loads(out) if out.lstrip().startswith("[") else []
    found: dict[str, list[dict]] = {}
    for r in rows:
        found.setdefault(r["object_uri"], []).append({"state": r["state"], "refused": r.get("refused")})
    return found


def sha_seen_elsewhere(
    *, project_id: str, max_bytes_billed: int, file_sha256: str, object_uri: str, run: Runner = subprocess.run
) -> bool:
    """AD-3 duplicate: another object_uri with this sha is the original.

    It counts only if it was not itself rejected_duplicate and either got past `landed` or recorded its
    first `landed` before this URI did (a copy's discovery-only `landed` row never outranks an older original).
    """
    sql = (f"WITH o AS (SELECT object_uri, LOGICAL_OR(state = 'rejected_duplicate') AS dup, "
           "LOGICAL_OR(state != 'landed') AS past, MIN(IF(state = 'landed', recorded_at, NULL)) AS first_landed "
           f"FROM `{project_id}.ops.file_lifecycle` WHERE file_sha256 = @sha GROUP BY object_uri), "
           "me AS (SELECT MIN(first_landed) AS t FROM o WHERE object_uri = @uri) "
           "SELECT COUNT(*) AS n FROM o, me WHERE o.object_uri != @uri AND NOT o.dup "
           "AND (o.past OR me.t IS NULL OR o.first_landed < me.t)")  # fmt: skip
    args = [*bq_query_args(project_id, max_bytes_billed), "--format=json",
            f"--parameter=sha:STRING:{file_sha256}", f"--parameter=uri:STRING:{object_uri}"]  # fmt: skip
    out = run([*args, sql], check=True, capture_output=True, text=True).stdout
    rows = json.loads(out) if out.lstrip().startswith("[") else []
    return bool(rows) and int(rows[0]["n"]) > 0
