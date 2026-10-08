---
title: 'Run-identity stub'
type: 'feature'
ticket: '10'
created: '2026-10-08'
status: 'built'
baseline_revision: '05270c123c49ac08228ae38bc12ccbb8584aa59e'
route: 'oneshot'
route_source: 'auto'
risk: 'medium'
review: 'quick'
review_source: 'pinned'
lenses_ran: [quick]
review_loop_iteration: 0
followup_review_recommended: true
context: []
warnings: []
deferred:
  - summary: >-
      BigQueryBackend has no unit test (SQL, bq parameter parsing with colons in ISO timestamps).
    evidence: |-
      Only FakeBackend is tested; the live path is optional (`make run-stub`) and has not been run.
    location: >-
      pipeline/runner.py
    severity: low
---

<intent-contract>

## Intent

**Problem:** No component mints `run_id` or enforces one pipeline run per client (AD-24, AD-17).

**Approach:** `pipeline/runner.py` mints `run_id`, takes `ops.run_lock` (lock_key, run_id, acquired_at, expires_at; entry 7) by insert-if-absent with TTL from config `run.lock_ttl_minutes` (default 120), passes `run_id` to a no-op task and releases the lock. A fake backend backs pytest; a BigQuery MERGE backend backs the optional `make run-stub`. Lock key = profile name.

</intent-contract>

## Implementation Notes

Oneshot: about 150 lines in a new package plus one config key. Files: `pipeline/{__init__,runner,test_runner}.py`, `config/defaults.yaml` + `profile.schema.json` (`run.lock_ttl_minutes`), `config/test_load.py` fixture, `config/resolved.yaml`, `pyproject.toml` testpaths, `Makefile` `run-stub`. BigQuery backend shells out to `bq` to avoid a new dependency.

## Review Triage Log

### 2026-10-08 — Review pass
- verdicts: 6 findings — high 0, medium 2, low 4, false 0, maybe-false 0
- findings:
  - `[medium]` `[patch]` bq queries lack a bytes cap (AD-16) — `BigQueryBackend` now takes `cost.max_bytes_billed` and passes `--maximum_bytes_billed`.
  - `[medium]` `[patch]` lock read-back is not deterministic under concurrent inserts — SELECT now `ORDER BY acquired_at, run_id LIMIT 1` so all racers agree on one holder; a takeover between MERGE and SELECT makes the loser see the new holder and exit.
  - `[low]` `[patch]` empty read-back IndexError / uncaught CalledProcessError — empty rows raise LockHeld; main catches CalledProcessError and exits 1.
  - `[low]` `[defer]` no BigQueryBackend unit test — deferred; live path optional.
  - `[low]` `[reject]` `run-stub` depends on `resolve` and rewrites resolved.yaml — same pattern as `apply`/`tf-bootstrap`; resolve is deterministic for the default profile.
  - `[low]` `[patch]` dead `"default": 120` in schema — removed; defaults.yaml supplies it.

## Verification

**Commands:**
- `uv run pytest pipeline/` -- expected: first run holds lock, concurrent run raises/exits "lock held", expired lock taken over.
- `make validate` -- expected: pass.

## Auto Run Result

- **Summary:** run-identity stub with lock-by-TTL; fake and BigQuery backends; `run.lock_ttl_minutes` config key.
- **Review:** 4 patched (2 medium, 2 low), 1 deferred, 1 rejected (run-stub resolve pattern matches existing targets).
- **Follow-up review recommended:** true (two medium patches). The unverified risk is the BigQuery MERGE/SELECT path, which has never run live; `make run-stub` would confirm it.
- **Verification:** `make validate` passes, 57 tests, including the three ticket cases in `pipeline/test_runner.py`.
