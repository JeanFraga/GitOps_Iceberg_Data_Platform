---
title: 'Full-size local run to landing and CI volume profile'
type: 'feature'
ticket: '9'
created: '2026-10-08'
status: 'built'
baseline_revision: '970491b6a553210f9ce0f4e5d0aeca017230e96f'
route: 'full'
route_source: 'auto'
risk: 'medium'
review: 'quick'
review_source: 'pinned'
lenses_ran: [quick]
review_loop_iteration: 0
followup_review_recommended: false
context: []
warnings: []
deferred:
  - summary: >-
      Budget guard compares one month of storage cost with budget minus existing landing storage cost, so it practically never trips.
    evidence: |-
      gcloud exposes no month-to-date spend; a real headroom needs a billing export to BigQuery. Full run estimate ~0.0034 USD/month vs 5 USD budget.
    location: >-
      datagen/estimate.py
    severity: medium
  - summary: >-
      make generate-upload after a full run lands stale CI output from datagen/out/.
    evidence: |-
      VOLUME=full no longer writes datagen/out/, generate-upload still reads it; help text does not warn.
    location: >-
      Makefile generate-upload
    severity: low
  - summary: >-
      Rerun still deletes and reloads mpi_eval.ground_truth for the seed (brief empty window).
    evidence: |-
      Pre-existing load_ground_truth behaviour; landing objects are not overwritten.
    location: >-
      datagen/upload.py load_ground_truth
    severity: low
---

<intent-contract>

## Intent

**Problem:** `make generate VOLUME=full` writes every full-size file into `datagen/out/` inside the repo tree and never lands it; there is no cost estimate, no budget guard, no run summary of bytes, and `.env` cannot influence sizing.

**Approach:** For `VOLUME=full`, generate into a temp dir outside the repo, print a size/storage-cost estimate, check it against NFR-1 budget headroom, then stream each landing file to `gs://$PROJECT-landing/` with `--if-generation-match=0` (reusing `datagen/upload.py`), load ground truth, delete the temp copy, and print a run summary with total bytes. `VOLUME=ci` keeps the existing local behaviour (~5,000 members). `.env` keys fill sizing only where config leaves them unset; config wins on conflict.

## Boundaries & Constraints

**Always:** CLI tools only (`gcloud storage`, `bq --project_id=...`); every gcloud write non-interactive; idempotent rerun (already-landed SHA reported, never overwritten); sizes come from `config/resolved.yaml` `datagen.volume_profiles` so size changes need no code change; determinism unchanged (same seed → same SHA-256); generated full-size files never under the repo tree.
**Never:** change `infra/` or the `mpi_eval.ground_truth` schema (the missing `noise_type` column stays dropped by `--ignore_unknown_values`); add Dataproc path (parked); commit generated data.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Full run | `generate --volume full` | estimate printed first; files land; summary prints file count and total bytes equal to sum of landed file sizes; temp dir removed | none |
| Rerun | same seed, objects present | every file reported `skip (already landed)`; no `cp` issued | none |
| Over budget | estimate > headroom, no FORCE | exit 1, `refusing upload ... set FORCE=1`, nothing uploaded | non-zero exit |
| Over budget forced | estimate > headroom, `FORCE=1` | warning printed, upload proceeds | none |
| .env sets volume differing from config | `DATAGEN_VOLUME_PROFILE=full` in env, config `ci` | config value used; warning `config wins` | none |
| .env fills unset key | config profile lacks `years`, env `DATAGEN_YEARS=2` | env value used | none |
| CI volume | `generate --volume ci` | output in `datagen/out/`, payer_b members file ≈5,000 distinct members (4,500–5,500) | none |

</intent-contract>

## Code Map

- `datagen/__main__.py` -- CLI; add full-volume path (estimate → guard → generate to tmp → upload → summary) and `--force` flag (also `FORCE=1` env).
- `datagen/generate.py` -- `generate(ctx, out=OUT)` already takes an out dir; reuse with a `tempfile.mkdtemp()` dir outside the repo (default `$TMPDIR`). Do not change file contents/ordering (determinism).
- `datagen/upload.py` -- `upload(cfg, out, run)`, `upload_landing` (SHA-prefix skip, `--if-generation-match=0`), `load_ground_truth`; reuse; extend the returned log/summary with byte totals (sum of local file sizes landed or already present).
- `datagen/config.py` -- `resolve_volume`; add `.env` merge (read `REPO/.env` simple KEY=VALUE plus `os.environ`; keys `DATAGEN_VOLUME_PROFILE`, `DATAGEN_RECORDS_PER_FILE`, `DATAGEN_YEARS`); config wins on conflict with a stderr warning.
- `datagen/estimate.py` (new) -- estimate bytes per profile without building full output: scale from a small calibration (e.g. bytes/record of the CI-size sample or a fixed per-feed constant measured from a tiny generate) × records_per_file × files; storage cost = GB × 0.020 USD/GB-month (us-east1 Standard, constant in module). Headroom = `budget.amount_usd` − monthly storage cost of current landing usage (`gcloud storage du -s gs://$PROJECT-landing/`).
- `Makefile` -- `generate` target passes `$(if $(FORCE),--force)`; help text mentions full-volume landing.
- `datagen/tests/` -- add `test_full_run.py` using the existing `FakeRun` pattern in `test_datagen.py:123`.

## Tasks & Acceptance

**Execution:**
- [x] `datagen/config.py` -- `.env` override merge with config-wins rule -- PRD FR-1 sizing contract.
- [x] `datagen/estimate.py` -- size and cost estimate plus headroom check -- NFR-1 guard.
- [x] `datagen/upload.py` -- byte totals in summary; accept out dir -- run summary for verify.
- [x] `datagen/__main__.py` -- full-volume streaming path, `--force`, temp dir cleanup in `finally` -- no full-size file in repo tree.
- [x] `Makefile` -- FORCE passthrough.
- [x] `datagen/tests/test_full_run.py` -- one test per I/O matrix row with fake runner -- matrix coverage.

**Acceptance Criteria:**
- Given the demo profile, when `make generate VOLUME=full` runs, then output begins with the estimate and ends with a summary whose total bytes equals `gcloud storage du -s gs://$PROJECT-landing/` for the landed objects of this run.
- Given that run completed, when it is rerun, then every object is reported already present and none overwritten.
- Given `make generate VOLUME=ci`, then the payer_b members file holds about 5,000 members and `git status --porcelain` shows no generated file after either run.

## Implementation Notes

- Estimate calibrates from a 300-record generate (same seed/years/drift) scaled linearly; live full run estimated 183,731,900 B vs actual 182,242,735 B (0.8% high).
- CI members: payer_b members are split across the base file and drift-slice files (3,601 + 449 + 449 + 499); the ~5,000 check counts distinct member_id across all payer_b members files.
- Live verify 2026-10-08: first full run landed 55 files, summary 182,242,735 B = du delta (183,571,423 − 1,328,688 pre-existing); rerun skipped all 55; `git status` clean of generated files.

## Plan Change Log

## Review Triage Log

### 2026-10-08 — Review pass
- verdicts: 11 findings — high 0, medium 2, low 7, false 2, maybe-false 0
- findings:
  - `medium` `patch` du failure returned 0 so guard silently off; non-numeric output tracebacks — landing_bytes now raises EstimateError (caught in main, prints error); test added.
  - `medium` `defer` guard practically never trips (storage-only headroom) — needs billing export; recorded in deferred.
  - `false` `reject` .env keys never apply with shipped config — intent says config wins on conflict; env fills only unset keys, as specified.
  - `low` `reject` read_env merges all of os.environ — only DATAGEN_* keys are read; stray-warning case is rare and fix adds filtering.
  - `low` `patch` FORCE semantics differ between Makefile and env — env FORCE now any non-empty value, matching Makefile.
  - `low` `defer` generate-upload after full run lands stale datagen/out — deferred.
  - `false` `reject` summary bytes include already-present files — summary line states "landed or already present"; AC verified as delta on live bucket.
  - `low` `defer` rerun reloads ground truth — pre-existing upload behaviour, deferred.
  - `low` `reject` TMPDIR inside repo not guarded — unusual setup, fix adds guard complexity.
  - `low` `reject` no test of git status for CI output — datagen/out is gitignored and live check passed.
  - `low` `reject` calibration generate on every full run — cost only, ~seconds.

## Design Notes

Headroom uses only CLI-observable data: Cloud Billing exposes no month-to-date spend via gcloud, so headroom = budget minus the monthly storage cost of what landing already holds. Recorded as an assumption. Landing may hold objects from earlier CI runs (different SHAs); the summary total covers this run's files, and verify compares against `du` when landing held only this run's objects (empty bucket first, or compare per-prefix).

## Verification

**Commands:**
- `uv run pytest datagen -q` -- expected: all pass
- `make lint` -- expected: clean
- `make generate VOLUME=full` then rerun -- expected: summary bytes match `gcloud storage du -s`; rerun all skips
- `make generate VOLUME=ci && git status --porcelain` -- expected: empty status

## Auto Run Result

- Summary: `VOLUME=full` estimates size/cost, guards against budget headroom (FORCE=1 overrides), generates to a temp dir outside the repo, lands each file with `--if-generation-match=0`, loads ground truth, prints a byte summary, removes the temp dir. `.env` fills unset sizing keys; config wins on conflict.
- Files: `datagen/estimate.py` (new estimate/headroom), `datagen/__main__.py` (run_full, --force), `datagen/config.py` (.env merge), `datagen/upload.py` (byte totals summary), `Makefile` (FORCE passthrough), `datagen/tests/test_full_run.py` (matrix tests).
- Review: 2 patches (du fail-closed, FORCE semantics), 3 deferred, 6 rejected (reasons in triage log).
- Follow-up review recommended: false (patched: 1 medium, 1 low).
- Verification: pytest 114 passed; make lint clean; live full run landed 55 files, summary 182,242,735 bytes = du delta (1,328,688 -> 183,571,423); rerun all skipped; mpi_eval.ground_truth seed 20261008 = 78,970 rows; VOLUME=ci ~4,998 distinct members; git status clean.
- Residual risks: budget guard weak (deferred); ground truth noise_type dropped by --ignore_unknown_values (no column in table).
