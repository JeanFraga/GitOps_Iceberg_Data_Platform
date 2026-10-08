"""Run-identity stub (AD-24, AD-17): mint run_id, take ops.run_lock, run a no-op task.

Usage: python -m pipeline.runner [--backend bigquery]
Only this runner mints run_id; tasks receive it as an argument. The lock is
insert-if-absent with a TTL from config `run.lock_ttl_minutes`; an expired lock is
taken over. A second run while the lock is live exits nonzero with "lock held".
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Protocol

import yaml

RESOLVED = Path(__file__).resolve().parent.parent / "config" / "resolved.yaml"


@dataclass(frozen=True)
class Lock:
    lock_key: str
    run_id: str
    acquired_at: datetime
    expires_at: datetime


class LockBackend(Protocol):
    def acquire(self, lock: Lock, now: datetime) -> str:
        """Insert lock if absent or expired; return the run_id now holding lock_key."""

    def release(self, lock_key: str, run_id: str) -> None: ...


class LockHeld(Exception):
    pass


class FakeBackend:
    """In-memory ops.run_lock for tests."""

    def __init__(self) -> None:
        self.rows: dict[str, Lock] = {}

    def acquire(self, lock: Lock, now: datetime) -> str:
        current = self.rows.get(lock.lock_key)
        if current is None or current.expires_at <= now:
            self.rows[lock.lock_key] = lock
        return self.rows[lock.lock_key].run_id

    def release(self, lock_key: str, run_id: str) -> None:
        if (row := self.rows.get(lock_key)) and row.run_id == run_id:
            del self.rows[lock_key]


class BigQueryBackend:
    """ops.run_lock in live BigQuery via the bq CLI (optional; `make run-stub`)."""

    def __init__(self, project_id: str, max_bytes_billed: int) -> None:
        self.table = f"`{project_id}.ops.run_lock`"
        self.max_bytes_billed = max_bytes_billed

    def _query(self, sql: str, **params: str) -> list[dict]:
        args = ["bq", "query", "--use_legacy_sql=false", "--format=json", "--quiet"]
        args.append(f"--maximum_bytes_billed={self.max_bytes_billed}")
        args += [f"--parameter={k}:STRING:{v}" for k, v in params.items()]
        out = subprocess.run([*args, sql], check=True, capture_output=True, text=True).stdout
        return json.loads(out) if out.strip() else []

    def acquire(self, lock: Lock, now: datetime) -> str:
        self._query(
            f"MERGE {self.table} t USING (SELECT @key AS lock_key) s ON t.lock_key = s.lock_key "
            "WHEN MATCHED AND t.expires_at <= TIMESTAMP(@now) THEN UPDATE SET run_id = @run, "
            "acquired_at = TIMESTAMP(@acq), expires_at = TIMESTAMP(@exp) "
            "WHEN NOT MATCHED THEN INSERT (lock_key, run_id, acquired_at, expires_at) "
            "VALUES (@key, @run, TIMESTAMP(@acq), TIMESTAMP(@exp))",
            key=lock.lock_key,
            run=lock.run_id,
            now=now.isoformat(),
            acq=lock.acquired_at.isoformat(),
            exp=lock.expires_at.isoformat(),
        )
        # Concurrent inserts can leave two rows for one key; every reader picks the same earliest one.
        rows = self._query(
            f"SELECT run_id FROM {self.table} WHERE lock_key = @key ORDER BY acquired_at, run_id LIMIT 1",
            key=lock.lock_key,
        )
        if not rows:
            raise LockHeld(f"lock held: {lock.lock_key} changed during acquire")
        return rows[0]["run_id"]

    def release(self, lock_key: str, run_id: str) -> None:
        self._query(f"DELETE FROM {self.table} WHERE lock_key = @key AND run_id = @run", key=lock_key, run=run_id)


def mint_run_id(now: datetime) -> str:
    return f"{now:%Y%m%dT%H%M%SZ}-{uuid.uuid4().hex[:8]}"


def noop_task(run_id: str) -> str:
    """Placeholder task: receives run_id from the runner, never mints one."""
    return run_id


def run(
    backend: LockBackend, lock_key: str, ttl_minutes: int, now: datetime | None = None, release: bool = True
) -> str:
    """Mint run_id, take the lock or raise LockHeld, run the no-op task. Returns run_id."""
    now = now or datetime.now(UTC)
    run_id = mint_run_id(now)
    lock = Lock(lock_key, run_id, now, now + timedelta(minutes=ttl_minutes))
    holder = backend.acquire(lock, now)
    if holder != run_id:
        raise LockHeld(f"lock held: {lock_key} by run {holder}")
    try:
        noop_task(run_id)
    finally:
        if release:
            backend.release(lock_key, run_id)
    return run_id


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backend", choices=["bigquery"], default="bigquery")
    parser.parse_args(argv)
    cfg = yaml.safe_load(RESOLVED.read_text())
    try:
        backend = BigQueryBackend(cfg["project_id"], cfg["cost"]["max_bytes_billed"])
        run_id = run(backend, cfg["profile"], cfg["run"]["lock_ttl_minutes"])
    except (LockHeld, subprocess.CalledProcessError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(f"run {run_id} complete")
    return 0


if __name__ == "__main__":
    sys.exit(main())
