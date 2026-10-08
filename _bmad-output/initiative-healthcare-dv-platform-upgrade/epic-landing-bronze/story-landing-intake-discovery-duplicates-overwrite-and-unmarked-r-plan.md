---
title: 'Landing intake: discovery, duplicates, overwrite and unmarked refusal'
type: 'feature'
ticket: '4'
created: '2026-10-08'
status: 'built'
baseline_revision: '13679e7db7b32be101b15b76f0e3578e94662cc1'
route: 'full'
route_source: 'auto'
risk: 'medium'
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
      Nine demo CSVs were wrongly quarantined by the first live batch, before the per-file run_id fix.
    evidence: |-
      Batch mode shared one run_id, so the gate counted other files' branch rows. Bronze main was untouched. The files stay quarantined until E4 replay (quarantined -> landed).
    location: >-
      demo ops.file_lifecycle
    severity: medium
  - summary: >-
      The demo unmarked.csv has a plain landed row from before the refusal-detail fix, so every demo batch re-refuses it and exits 3.
    evidence: |-
      The fix only writes refusal detail for objects with no lifecycle rows. Remedy: append one landed row with {"refused":"unmarked"} for that URI (owner decision on a manual ops write).
    location: >-
      ingestion/discover.py pending
    severity: medium
  - summary: >-
      Discovery lists the whole bucket and passes all URIs as one bq array parameter, which will hit ARG_MAX or parameter limits as landing grows.
    evidence: |-
      list_landing uses gs://bucket/** and rows_for_uris sends a single --parameter with no chunking.
    location: >-
      ingestion/discover.py, ingestion/lifecycle.py rows_for_uris
    severity: medium
---

<intent-contract>

## Intent

**Problem:** Files reach Bronze only one at a time by explicit `FILE=`. Nothing lands a local directory under AD-3, discovers what is pending, or applies the AD-3 duplicate rule.

**Approach:** Add `make land PROFILE=demo SRC=<dir>`, which reuses `datagen/upload.py` helpers to `cp --if-generation-match=0` each `<source>/<feed>/<file>` under `source=/feed=/ingest_date=/sha256=/<name>`. Add batch mode to `make bronze` when FILE is empty. It lists the landing bucket, joins the list against `ops.file_lifecycle`, and runs each pending object through the existing `load()`. Before WAP, an object whose sha already has lifecycle rows under another `object_uri` gets `rejected_duplicate`.

## Boundaries & Constraints

**Always:** Discovery uses `gcloud storage ls` on the landing bucket, joined against `ops.file_lifecycle` by `object_uri`. Pending means an object that has no lifecycle row, or whose rows stop at `landed`. Keep the 3.2/3.3 WAP order, the landed-once rule, the skip across all `<feed>__*` tables, `_landed_sha256`, and the type-only error handlers. Log JSON lines on stderr with no row values. Every `bq` call passes `--project_id` and `--maximum_bytes_billed` (`lifecycle.bq_query_args`). An overwrite rejection is a JSON line `{"event":"land_rejected_overwrite","uri":...}` and does not abort the other files.

**Never:** Never list the catalog or Iceberg tables for discovery. Never delete or overwrite landing objects. Never write Bronze for an unmarked file, a non-CSV file or a duplicate. Never duplicate landing-path or cp logic in the Makefile. Never apply Terraform here, because the stale demo tf-lock is still unresolved.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|---|---|---|---|
| HAPPY_PATH | new marked CSV landed, no lifecycle rows | `landed` -> `bronze_appended` -> `reconciled` | exit 0 |
| Overwrite rejected | `make land` of the same file twice on the same date (same path) | second cp fails the generation precondition; `land_rejected_overwrite` logged; object unchanged | land continues; exit 0 if that was the only issue (rejection is expected AD-3 behavior) |
| Duplicate sha, other name | copy landed as `members_copy.csv` (same sha, new uri) | `landed` then `rejected_duplicate` for that uri; no Spark write | logged `rejected_duplicate`; batch continues |
| Re-delivered name, new content | edited `members.csv` with the same name | new sha, so new path and new object; loads to `reconciled` | exit 0 |
| Unmarked refusal | `tests/fixtures/marker/unmarked/members.csv` landed | `landed` recorded once by discovery, then refused with a log line; no Bronze rows and no `bronze_appended` | per-file code 3; batch continues; batch exit nonzero |
| Non-CSV in discovery | `.jsonl` / `.x12` object pending | skipped with `skipped_unsupported_format` log line, no lifecycle row | not counted as a failure until entry 5 (the single-file path keeps exit 5) |
| One file fails mid-batch | 3 pending, the 2nd raises (gate/Spark/bq) | 1st and 3rd still load | batch exit 1; a summary line lists the failed uris |
| RELOAD | batch rerun, nothing new | every object is skipped by the join or by `skipped_already_appended` | exit 0 |

</intent-contract>

## Code Map

- `ingestion/__main__.py` -- `main()`/`load()`; make `--file` optional and add batch mode with per-file exit aggregation.
- `ingestion/discover.py` (new) -- bucket listing, URI parse (`URI_RE`), join with lifecycle, pending list.
- `ingestion/lifecycle.py` -- add `rows_for_uris`/`sha_seen_elsewhere` queries, both parameterized.
- `ingestion/marker.py` -- `check_marker`/`UnmarkedFile` (reuse).
- `datagen/upload.py` -- extract a `land_file(path, source, feed, bucket, date, run)` helper with no sha pre-skip, and keep the old `upload_landing` behavior on top of it.
- `ingestion/land.py` (new) -- walk SRC `<source>/<feed>/<file>`, call `land_file`, log the results.
- `Makefile` -- `land` target; `bronze` without FILE runs discovery.
- `config/standards/lifecycle.yaml` -- `landed -> rejected_duplicate` already allowed; no change.

## Tasks & Acceptance

**Execution:**
- [x] `datagen/upload.py` -- factor out `land_file`, returning landed / rejected_overwrite -- one shared landing implementation.
- [x] `ingestion/land.py` + `ingestion/__main__.py` (`land` subcommand or `--land SRC`) -- land a directory.
- [x] `ingestion/discover.py`, `ingestion/lifecycle.py` -- list bucket, join lifecycle, return pending uris.
- [x] `ingestion/__main__.py` -- duplicate check after landed-once and before the skip and WAP; batch loop with try per file; non-CSV skip; aggregate exit.
- [x] `Makefile` -- `land` (SRC required) and FILE-less `bronze`; add both to `.PHONY`.
- [x] `ingestion/tests/test_intake.py` -- every matrix row against the fake ops backend and a fake gcloud runner.

**Acceptance Criteria:**
- Given an empty FILE, when `make bronze PROFILE=demo` runs, then the only sources of discovery are `gcloud storage ls` and `ops.file_lifecycle` (asserted with the fake runner).
- Given a `rejected_duplicate` object, when a later batch runs, then it is not retried (terminal state).
- Given any log line, then it carries no row values.

## Implementation Notes

- Batch mode mints one run_id per file (the batch lock stays under the batch run_id). A first live run shared one run_id, so the reconcile gate (which reads branch rows by `_run_id`) counted rows from earlier files in the same table, and 9 previously landed datagen CSVs were quarantined with RECONCILE_FAIL (count). Main was untouched. Those files are now terminal for discovery until E4 replay.
- The duplicate test ignores other URIs that are themselves `rejected_duplicate`, so an original that failed mid-batch is not later rejected because of its own copy.
- Overwrite is detected from the gcloud cp stderr (`412` / `precondition`); any other cp failure raises.

## Plan Change Log

## Review Triage Log

### 2026-10-08 — Review pass
- verdicts: 6 findings — high 0, medium 4, low 2, false 0, maybe-false 0
- findings:
  - `medium` `patch` A bare "412" matched the sha, so other cp errors were labelled overwrites. Fixed: PRECONDITION_RE; test added.
  - `medium` `patch` An unmarked file was retried forever and batches exited nonzero. Fixed: the refusal detail on the landed row excludes it from pending; two-run test.
  - `medium` `patch` A copy's discovery-only landed row could make the original rejected_duplicate. Fixed: the original must be past landed or landed earlier; test added.
  - `medium` `defer` Discovery lists the whole bucket and sends one unbounded bq parameter. Needs chunking or prefix-scoping later.
  - `low` `patch` land_dir landed dot-files and aborted on the first cp error. Fixed: dot-files are skipped, errors are per-file, exit nonzero.
  - `low` `reject` upload_landing loses the original stderr on a lost race. Error text only; the behavior is unchanged.

## Auto Run Result

- Summary: `make land` lands files under AD-3 with overwrite rejection. `make bronze` with no FILE discovers pending objects by bucket listing joined to ops.file_lifecycle, handles rejected_duplicate and unmarked refusal, and loads the rest through WAP with a per-file run_id.
- Files: datagen/upload.py (land_file), ingestion/land.py, ingestion/discover.py, ingestion/lifecycle.py, ingestion/__main__.py, Makefile, tests.
- Review: 4 patched (3 medium, 1 low), 1 deferred plus 2 incident items deferred, 1 rejected.
- Follow-up review recommended: true. Three medium patches changed discovery and duplicate semantics and are not re-run live on demo.
- Verification: pytest ingestion pipeline config datagen gave 263 passed. make validate passed. Before the patches, demo live showed an overwrite rejected, the copy rejected_duplicate, the edited file reconciled, and the unmarked file refused.
- Residual risk: 9 demo files are wrongly quarantined, demo batches exit 3 until the unmarked row is remediated, and the IAM grant is still unapplied.

## Design Notes

AD-3 paths embed sha and ingest_date, so a re-delivered name with new content gets a new path. An overwrite collision only happens for the same bytes on the same date. `upload_landing` pre-skips by sha, so it never hits the precondition. `land` therefore calls `land_file` directly, letting the overwrite surface and a renamed copy land, which discovery then marks `rejected_duplicate`. The duplicate test is: the sha has a lifecycle row whose `object_uri` differs from this object's. The original object keeps its own state.

## Verification

**Commands:**
- `uv run pytest ingestion pipeline config datagen` -- expected: all pass, Spark tests not skipped.
- `make validate` -- expected: pass.
- `make land PROFILE=demo SRC=<tmpdir with payer_b/members/members.csv>` run twice -- expected: the second run logs `land_rejected_overwrite`.
- Copy to `members_copy.csv`, edit `members.csv`, add unmarked `payer_b/members/unmarked.csv`, `make land`, then `make bronze PROFILE=demo` -- expected: nonzero exit (unmarked); copy `rejected_duplicate`; edited `reconciled`.
- `bq --project_id=gitops-iceberg-data-platform query --nouse_legacy_sql --maximum_bytes_billed=1000000000 --format=json --quiet "SELECT object_uri, ARRAY_AGG(state ORDER BY recorded_at DESC LIMIT 1)[OFFSET(0)] s FROM ops.file_lifecycle WHERE DATE(recorded_at)=CURRENT_DATE() GROUP BY 1"` -- expected: the states above; the unmarked uri has exactly one `landed` row (discovery records `landed` for every listed object before the marker check), and no other state.
