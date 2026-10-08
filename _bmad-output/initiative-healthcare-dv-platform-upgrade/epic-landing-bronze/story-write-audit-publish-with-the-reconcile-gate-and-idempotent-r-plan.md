---
title: 'Write-audit-publish with the reconcile gate and idempotent reload'
type: 'feature'
ticket: '2'
created: '2026-10-08'
status: 'built'
baseline_revision: '61702cbec747429b880d9124fa8f5b72d97fd934'
route: 'full'
route_source: 'auto'
risk: 'high'
review: 'quick'
review_source: 'pinned'
lenses_ran: ['quick']
review_loop_iteration: 0
followup_review_recommended: true
context:
  - '{project-root}/_bmad-output/initiative-healthcare-dv-platform-upgrade/epic-landing-bronze/epic-landing-bronze.md'
warnings: []
deferred:
  - summary: >-
      BigLake IAM grant for runtime-sa is not applied to demo (carried from 3.1).
    evidence: |-
      Stale Terraform state lock 1791492655983054; the owner must force-unlock, then make apply. Local runs use user ADC.
    location: >-
      infra/modules/iam/main.tf
    severity: medium
---
<intent-contract>
## Intent
**Problem:** Entry 1 appends straight to Bronze main. A reload duplicates rows, nothing proves the rows match the landed bytes, and every run writes another `landed` row, even when the run fails.
**Approach:** Wrap the append in AD-4 write-audit-publish. First check `ops.file_lifecycle`: skip if the file already has `bronze_appended`. Otherwise write to branch `wap_<sha8>`, then run the reconcile gate. The gate compares the record count and the per-record SHA-256 of the branch against the landing object, split per records.yaml. Append `bronze_appended` once the branch write commits. On pass, fast-forward main and append `reconciled`. On fail, leave main as it is and append `quarantined` plus one `ops.quarantine` row with reason `RECONCILE_FAIL`.
## Boundaries & Constraints
**Always:**
- Keep entry 1's pins: pyspark 4.0.4, Java 21, `iceberg-spark-runtime-4.0_2.13:1.12.0` plus `iceberg-gcp-bundle:1.12.0`.
- Keep the lineage column name `_landed_sha256`. BigQuery reserves the `_file_` prefix.
- Read from BigQuery by the four-part name `<project>.<project>-warehouse.<ns>.<table>`.
- Every `bq` call carries `--project_id` and `--maximum_bytes_billed` from resolved.yaml.
- Use non-interactive flags only (`--quiet`, `-auto-approve`).
- Logs, errors, `detail` JSON and `ops.quarantine` carry counts, hashes and ordinals only, never row values. `raw_line` stays NULL.
- Each delivery adds exactly one snapshot to main. Its summary carries `run_id` and `file_sha256`.
- Write `landed` once per file_sha256: skip it when a `landed` row already exists. This absorbs the 3.1 orphan-row item.
**Never:**
- Never issue UPDATE, DELETE, MERGE, `expire_snapshots`, `rollback_to_snapshot` or row rewrites.
- No fingerprint routing (3.3), discovery or duplicates (3.4), or NDJSON/X12 (3.5).
- If branch writes or `fast_forward` fail on BigLake REST, change no pin and add no non-WAP fallback. Record the finding and mark the ticket blocked.
## I/O & Edge-Case Matrix
| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|---|---|---|---|
| PASS | tracer CSV, no lifecycle rows | branch written, gate passes, main fast-forwarded (+1 snapshot), lifecycle `landed`, `bronze_appended`, `reconciled` | none |
| TAMPER_COUNT | a branch row dropped or added (test hook) | gate fails, main snapshot count and rows unchanged, `quarantined` plus quarantine row `RECONCILE_FAIL`, detail `{expected, actual}` counts | nonzero exit; log has error type only |
| TAMPER_HASH | one branch `_raw_line` altered, count equal | as TAMPER_COUNT; detail gives mismatch count and first mismatching `_line_ordinal` | nonzero exit |
| RELOAD | `bronze_appended` exists for the sha | no Spark write, no new snapshot, no new lifecycle row; logs `skipped_already_appended` | exit 0 |
| FAILURE_MID_WAP | error after the branch write, before fast-forward | main untouched; the stale `wap_<sha8>` is replaced on the next attempt (`CREATE OR REPLACE BRANCH`) | nonzero exit, no `bronze_appended` |
| RAGGED_ROW | row field count != header | still loaded (`_raw_line` exact); `ragged_rows` count in `reconciled` detail (absorbs the 3.1 item) | none |
</intent-contract>
## Code Map
- `ingestion/__main__.py` -- `load()` orchestration. Add the skip check, the landed-once rule and the WAP sequence; keep the type-only error handlers.
- `ingestion/bronze.py` -- `append()` becomes `write_branch()`, `branch_rows()` and `publish()` (fast-forward). The snapshot is looked up by the `run_id` summary.
- `ingestion/reconcile.py` (new) -- a pure function: (landing records, branch rows) -> pass/fail plus counts, without Spark.
- `ingestion/records.py` -- `split()`, the record-byte source shared with the gate.
- `ingestion/lifecycle.py` -- `record()`. Add `latest_states(sha)` (a parameterized `bq query`) and `quarantine()` for `ops.quarantine`.
- `config/standards/lifecycle.yaml` -- read only (E1-owned). There is no `landed -> quarantined` transition; see Design Notes.
- `infra/modules/bq_ops/schemas/ops.quarantine.json` -- columns `file_sha256, line_ordinal, reason, raw_line, run_id, quarantined_at`. There is no `detail` column.
- `pipeline/runner.py` -- `run(task=...)` and `mint_run_id`; unchanged.
- `ingestion/tests/` -- `test_spark_local.py` (Hadoop catalog in tmp_path), `test_main.py` (fake ops backend).
## Tasks & Acceptance
**Execution:**
- [x] `ingestion/reconcile.py` -- count and per-record SHA-256 comparison over `_line_ordinal`-aligned records -- the gate is unit-testable without Spark.
- [x] `ingestion/bronze.py` -- create the table if absent, then `CREATE OR REPLACE BRANCH wap_<sha8>` and append via `writeTo(ident.branch_wap_<sha8>)` with `snapshot-property.run_id` and `.file_sha256`. Read the branch rows for this run_id, then publish with `CALL <cat>.system.fast_forward('<ns>.<tbl>', 'main', 'wap_<sha8>')` -- AD-4 WAP.
- [x] `ingestion/lifecycle.py` -- add a `latest_states` lookup and a `quarantine` insert -- for the idempotent skip and RECONCILE_FAIL.
- [x] `ingestion/__main__.py` -- order the run as: skip check, landed-once, branch write plus `bronze_appended`, gate, then publish plus `reconciled`, or `quarantined` plus a quarantine row. The BigQuery read proof runs after publish.
- [x] `ingestion/tests/` -- one test per matrix row. The local-Spark tamper test asserts that the main snapshot count is unchanged and that the fake backend got `quarantined` and `RECONCILE_FAIL`.
- [x] Live demo run, twice, recorded under Implementation Notes.

**Acceptance Criteria:**
- Given a fresh table for the tracer sha, when `make bronze` runs twice, then the Bronze count is 720 after both runs and main gained exactly one snapshot, whose summary has `run_id` and `file_sha256`.
- Given those runs, when `ops.file_lifecycle` is queried for the sha, then the latest state is `reconciled` and the second run added no rows.
- Given `git grep -nE "expire_snapshots|DELETE FROM|UPDATE |MERGE INTO" ingestion`, then there are no matches.
## Implementation Notes
- Local Spark (Hadoop catalog): an empty table has no main head, so `CREATE OR REPLACE BRANCH` fails. `write_branch` uses `DROP BRANCH IF EXISTS` and then `CREATE BRANCH` on an empty table, and `CREATE OR REPLACE BRANCH` otherwise. On a fresh table the branch starts from an empty snapshot, so main's ancestry includes that empty snapshot. Main's history log (`.history`) gains exactly one entry, the tagged WAP snapshot.
- BigLake REST probe: the branch write, `CREATE BRANCH` and `system.fast_forward` all worked live on the demo project, with no pin change. Before publish, BigQuery's four-part read saw 0 rows for the run (`bigquery_pre_publish`), so BigQuery reads main only.
- Live demo, 2026-10-08, `make bronze PROFILE=demo FILE=<tracer> TABLE_SUFFIX=_wap`:
  - Attempt 1 (run 20261008T222833Z-75e42749) wrote the branch and `bronze_appended`, then crashed in `bq_count` (`int(None)` on 0 rows; fixed). This was a real FAILURE_MID_WAP: main was untouched.
  - Attempt 2 (run 20261008T223042Z-3dad4d1c) replaced the stale branch, passed the gate, fast-forwarded and recorded `reconciled`. Exit 0.
  - Attempt 3 logged `skipped_already_appended`. Exit 0.
  - BigQuery `COUNT(*)` on `members__era_2024_wap` returned 720. Main history has 1 entry, whose summary carries run_id 20261008T223042Z-3dad4d1c and file_sha256 6b79bc0b…. One orphan tagged snapshot from attempt 1 sits on no ref and is not expired (Never rule).
  - Latest lifecycle state is `reconciled`. No new `landed` row was written (landed-once). `ops.quarantine` is empty.
- `make bronze` accepts an optional `TABLE_SUFFIX` that passes `--table-suffix` to the loader. Only the demo uses it.

## Plan Change Log
- The skip check is scoped per target table (`detail.table`). It fires only when the append finished: a `reconciled` or `quarantined` row exists for the table, or a pre-WAP `bronze_appended` row has no `branch` in its detail (the 3.1 rows). A `bronze_appended` left by a WAP attempt that died before the gate outcome is retried on a replaced branch. This is needed for the FAILURE_MID_WAP row ("the stale branch is replaced on the next attempt"), and it lets the `_wap` demo table load even though the sha already has 3.1's `bronze_appended`. A retry therefore writes `bronze_appended` twice, which `lifecycle.yaml` does not list as a transition.
- The tamper hook in tests is a monkeypatched `bronze.branch_rows` around the real branch read. There is no production flag.
- A ReconcileFail exits with code 4.

### 2026-10-08 — Review patch amendment
- After the review, a retry no longer writes a second `bronze_appended`. It is recorded only when none exists for the sha and table, which supersedes the earlier entry saying a retry writes it twice. The intent-contract matrix row FAILURE_MID_WAP ("no `bronze_appended`") holds only for failures during the branch write; after the branch commits, `bronze_appended` stays and a retry resumes from it.

## Review Triage Log

### 2026-10-08 — Review pass
- verdicts: 6 findings — high 1, medium 1, low 4, false 0, maybe-false 0
- findings:
  - `high` `patch` A crash after fast-forward but before reconciled caused a double publish on reload. Fixed: `published_snapshot` checks for the file_sha256 in main's lineage and recovers to reconciled; test added.
  - `medium` `patch` The matrix FAILURE_MID_WAP row conflicted with the code, and a retry wrote a second bronze_appended. Fixed: bronze_appended is written once per sha and table; the matrix scope is clarified in the Plan Change Log.
  - `low` `patch` A test name claimed a mid-WAP failure. Renamed to `test_failure_during_branch_write_leaves_no_bronze_appended`.
  - `low` `patch` ragged_count counted every non-UTF-8 record. Fixed: a row counts only when its field count differs from the header.
  - `low` `reject` row_bytes raises on corrupt base64 instead of failing the gate. Input comes only from our own writer; the run still exits nonzero with main untouched.
  - `low` `reject` landed is written before Spark, so an early failure leaves a lone landed row. landed-once holds, and a lone landed is a valid state that entry 4 discovery resumes.

## Auto Run Result

- Summary: AD-4 write-audit-publish. Writes to the wap_<sha8> branch, runs the Spark-free reconcile gate (count plus per-record SHA-256), fast-forwards main on pass, and quarantines with RECONCILE_FAIL on fail. Reload is idempotent, and recovery after a crash once published is handled. BigLake REST accepts branches and fast_forward on Iceberg 1.12.0.
- Files: ingestion/reconcile.py (new), ingestion/bronze.py, ingestion/lifecycle.py, ingestion/__main__.py, Makefile (TABLE_SUFFIX), ingestion/tests/*.
- Review: 4 patched (1 high, 1 medium, 2 low), 0 deferred, 2 rejected.
- Follow-up review recommended: true. The high patch (published_snapshot recovery) is verified only in local Spark, not on BigLake REST.
- Verification: `uv run pytest ingestion pipeline config` gave 77 passed. make validate passed. Before the patches, a live demo run on members__era_2024_wap gave 720 rows, one main history entry, reconciled, and a skip on the third run.
- Residual risk: the patches have not been re-run on demo. The runtime-sa BigLake IAM grant is still unapplied (stale tf lock, carried from 3.1).

## Design Notes
- **WAP on BigLake REST (risk):** Iceberg 1.12 supports branch writes (`branch_<name>` identifier or `spark.wap.branch`) and `system.fast_forward`. Both commit through REST `SetSnapshotRef` updates. That BigLake's REST catalog accepts non-main refs is unverified. Probe it first with a scratch table in the demo namespace. If it is rejected, stop with the ticket blocked. Another unverified point is that BigQuery's four-part read sees only main; assert this before the fast-forward in the live run. Prefer the explicit branch identifier over `spark.wap.branch`, which needs `write.wap.enabled=true` as a table property.
- **Tracer table:** it already holds 720 rows in one snapshot from 3.1, with no `bronze_appended` under WAP semantics, but 3.1 did write `bronze_appended`. The skip therefore fires on the first 3.2 run. To exercise WAP live, use a new table suffix (for example `members__era_2024_wap`), set by a `--table-suffix` flag that only the demo uses. Never drop or rewrite the 3.1 table.
- **Lifecycle order:** `bronze_appended` means the branch write committed, so a gate fail is `bronze_appended -> quarantined`, which `lifecycle.yaml` allows. A quarantined file is skipped on reload (it has `bronze_appended`); replaying it is E4's job (`quarantined -> landed`).
- Gate hash: `sha256(rec.raw)` over the record bytes per records.yaml, compared with `sha256(_raw_line bytes, base64-decoded when _raw_encoding=base64)`.
## Verification
**Commands:**
- `uv run pytest ingestion pipeline config` -- expected: all pass, with the Spark tests not skipped.
- `make validate` -- expected: pass.
- `make bronze PROFILE=demo FILE=gs://gitops-iceberg-data-platform-landing/source=payer_b/feed=members/ingest_date=2026-10-08/sha256=6b79bc0b9e8476901ed9a60f2707a4269df2e6288e5f1ea4e3bedf314fe7b10d/payer_b_members_2024.csv` run twice -- expected: both exit 0, and the second logs `skipped_already_appended`.
- `bq query --project_id=gitops-iceberg-data-platform --use_legacy_sql=false --maximum_bytes_billed=10737418240 'SELECT COUNT(*) FROM \`gitops-iceberg-data-platform.gitops-iceberg-data-platform-warehouse.bronze_payer_b.<table>\`'` -- expected: 720 after each run.
- In the same Spark session, `SELECT count(*), max(summary['run_id']), max(summary['file_sha256']) FROM <ident>.snapshots` -- expected: one WAP snapshot with both keys.
- `bq query --project_id=gitops-iceberg-data-platform --use_legacy_sql=false --maximum_bytes_billed=10737418240 --parameter=sha:STRING:6b79bc0b... 'SELECT state, run_id FROM ops.file_lifecycle WHERE file_sha256=@sha ORDER BY recorded_at'` -- expected: the latest state is `reconciled`.
