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
