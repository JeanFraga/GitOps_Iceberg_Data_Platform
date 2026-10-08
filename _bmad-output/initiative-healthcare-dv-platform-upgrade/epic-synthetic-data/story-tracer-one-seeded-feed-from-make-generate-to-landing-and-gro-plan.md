---
title: 'Tracer: one seeded feed from make generate to landing and ground truth'
type: 'feature'
ticket: '1'
created: '2026-10-08'
status: 'built'
baseline_revision: 'fa74781c5b886d7bd1ff08fb590e2cb526345c80'
route: 'full'
route_source: 'auto'
risk: 'medium'
review: 'quick'
review_source: 'pinned'
lenses_ran: [quick]
review_loop_iteration: 0
followup_review_recommended: false
context: []
warnings: [oversized]
deferred:
  - summary: >-
      Ground-truth reload is DELETE then bq load as two jobs; a failed load leaves the seed's rows empty until rerun.
    evidence: |-
      datagen/upload.py load_ground_truth runs two separate bq jobs; rerunning make generate-upload restores the rows.
    location: >-
      datagen/upload.py
    severity: low
  - summary: >-
      make generate PATH=... still fails at the pre-existing resolve prerequisite, which calls bare uv.
    evidence: |-
      Makefile resolve target predates this change; only the new recipes use the PATH-safe uv wrapper.
    location: >-
      Makefile
    severity: low
  - summary: >-
      Repo-wide make phi-scan never passes --names-file datagen/out/names.txt, so generated names are only checked when the scan is run by hand.
    evidence: |-
      No logs or run summaries exist yet to scan; wiring belongs with the first producer of logs/summaries.
    location: >-
      Makefile phi-scan
    severity: medium
---

<intent-contract>

## Intent

**Problem:** There is no synthetic data generator; every downstream epic (landing, Silver, Vault, MPI) needs deterministic, marked, source-shaped data with known identity truth.

**Approach:** Create a stdlib-only `datagen/` package with a pluggable feed registry, a seeded population, the shared Luhn NPI generator, and one feed (Payer B flat member CSV) end to end: local output with manifest and ground-truth contract, then upload to the landing bucket and `mpi_eval.ground_truth` via CLI tools.

## Boundaries & Constraints

**Always:** Same seed + volume profile gives byte-identical output (no timestamps, no unordered iteration, sorted rows). Every data file carries the token from `config/standards/guardrails.yaml` (`synthetic_marker.token`) within its first 4096 bytes: CSV as a first comment line `# <token>`; every JSON/JSONL record has `_synthetic` as its first key. Config is read from `config/resolved.yaml` (config wins over `.env`). Landing upload uses `gcloud storage cp --if-generation-match=0` to a path containing source, feed, ingestion date and the file SHA-256 (AD-3/FR-5). BigQuery calls pass `--maximum_bytes_billed` = `cost.max_bytes_billed` where the command supports it. New feeds are added as one module in `datagen/feeds/` with no edits elsewhere.

**Never:** No third-party data libraries (no Faker) — stdlib `random.Random(seed)` only. Never commit generated output (`datagen/out/` gitignored). Never write outside the landing bucket and `mpi_eval.ground_truth`. No X12/NCPDP/FHIR feeds, noise, drift or samples (later entries). Do not change `tools/guardrails.py` semantics beyond adding a `--names-file` option.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Generate twice | `make generate PROFILE=demo VOLUME=ci` x2 | identical `sha256sum` over `datagen/out/**` | No error expected |
| Unknown volume | `VOLUME=huge` | exit nonzero naming valid profiles | message on stderr |
| Re-upload same file | object already exists in landing | skipped as already landed, exit 0 | precondition failure not fatal when object exists |
| Re-load ground truth | rows for this generator_seed exist | prior rows for that seed deleted then reloaded; count equals member count | DML capped by bytes |
| Upload without generate | `datagen/out/manifest.json` missing | exit nonzero "run make generate first" | stderr |

</intent-contract>

## Code Map

- `config/defaults.yaml` -- add `datagen:` block: `seed: 20261008`, `eval_seed: 20261009`, `volume_profile: ci`, `volume_profiles: {ci: {records_per_file: 5000, years: 1}, full: {records_per_file: 30000, years: 2}}`.
- `config/schemas/profile.schema.json` -- `additionalProperties: false` at root: add required `datagen` object (seed/eval_seed ints, volume_profile enum ci|full, volume_profiles with ci and full, each records_per_file>=1, years>=1). Then `make resolve PROFILE=demo` to regenerate `config/resolved.yaml` (committed; `make check-resolved` gates it).
- `config/load.py` -- reuse as-is (deep merge, validation). Do not edit.
- `config/standards/guardrails.yaml` -- marker token source; `phi_scan.names` stays `[]`.
- `tools/guardrails.py` -- add `--names-file PATH` (one name per line, appended to `--names`). `tests/test_guardrails.py` holds existing tests; add one for `--names-file`.
- `infra/modules/bq_ops/schemas/` ground_truth schema: `generator_seed INT64, source_record_id STRING, source STRING, person_truth STRING` (all REQUIRED). Table exists live in dataset `mpi_eval`, 0 rows. Landing bucket `gs://<project_id>-landing` exists, empty.
- `pipeline/runner.py` -- pattern for reading `config/resolved.yaml` and shelling out to `bq` via subprocess; mirror it.
- `Makefile` -- `PROJECT_ID` var already defined; `PATH=` override trick for phi-scan/marker-check (`SCAN_PATH`, `TOOL_PATH`) — new targets that call uv must keep working when a caller passes `PATH=`. Add `datagen` to `.PHONY`.
- `pyproject.toml` -- add `datagen` to `[tool.pytest.ini_options].testpaths`.
- `.gitignore` -- add `datagen/out/`.

## Tasks & Acceptance

**Execution:**
- [x] `config/defaults.yaml`, `config/schemas/profile.schema.json`, `config/resolved.yaml` -- add datagen keys and schema; regenerate resolved -- config contract (AD-1).
- [x] `datagen/__init__.py`, `datagen/config.py` -- load resolved config, marker token; resolve volume profile (override arg wins over `datagen.volume_profile`) -- single config entry point.
- [x] `datagen/registry.py` -- discover feed modules in `datagen/feeds/` via `pkgutil`; each exposes `FEED` with `source`, `feed`, `generate(ctx) -> FeedOutput` (files + ground-truth rows + coverage spans); deterministic order by module name -- pluggable feeds (FR-1).
- [x] `datagen/population.py` -- seeded persons (person_id, first/last name, sex, dob, address) grouped into households; stdlib name lists embedded -- shared population.
- [x] `datagen/npi.py` -- `generate_npi(rng)`: 10-digit NPI with first two digits `29` (documented reserved synthetic range), check digit = Luhn over `80840` + first 9 digits; `is_valid_npi()` -- shared by entries 2, 4, 5.
- [x] `datagen/feeds/payer_b_members.py` -- Payer B flat member CSV, one file per year `payer_b_members_<year>.csv`, rows sorted by (subscriber_id, person_code), columns incl. member_id, subscriber_id, person_code (01 subscriber, 02 spouse, 03+ dependents), household_id, names, dob, sex, address, pcp_npi, coverage_start, coverage_end; `records_per_file` rows per file; same members across years with per-year coverage -- the tracer feed.
- [x] `datagen/generate.py` -- write `datagen/out/landing/<source>/<feed>/<file>`, `datagen/out/ground_truth/{person_truth,coverage_spans,encounter_claim}.jsonl` (sorted, `_synthetic` first key; an empty table holds one marker-only row `{"_synthetic": token}`), `datagen/out/manifest.json` (`_synthetic`, seed, volume_profile, files [{path, source, feed, sha256, records}], schema_drift: [], data_drift: []), `datagen/out/names.txt` (sorted unique full names); wipes `datagen/out/` first -- deterministic output.
- [x] `datagen/upload.py` -- for each manifest file: target `gs://<project>-landing/source=<s>/feed=<f>/ingest_date=<UTC today>/sha256=<sha>/<name>`; skip if any object with that sha already exists under `source=<s>/feed=<f>/`; else `gcloud storage cp --if-generation-match=0`. Ground truth: `bq query --use_legacy_sql=false --maximum_bytes_billed=<cap> 'DELETE FROM mpi_eval.ground_truth WHERE generator_seed=<seed>'` then `bq load --source_format=NEWLINE_DELIMITED_JSON --ignore_unknown_values mpi_eval.ground_truth person_truth.jsonl` (project via `--project_id`) -- landing + truth.
- [x] `datagen/__main__.py` -- CLI `python -m datagen generate [--volume ci|full]` and `python -m datagen upload`.
- [x] `Makefile` -- `generate: resolve` (`VOLUME ?=`, passes `--volume` when set) and `generate-upload: resolve`; help text.
- [x] `tools/guardrails.py`, `tests/test_guardrails.py` -- `--names-file`.
- [x] `datagen/tests/test_datagen.py` -- determinism (two runs into tmp dirs equal hashes), marker in every data file, manifest shape and sha matches file bytes, every CSV member in person_truth (and counts match), NPI Luhn validity and prefix, registry discovers a feed, unknown volume errors, upload command construction with subprocess mocked (skip-if-exists, delete-then-load with cap).
- [x] `.gitignore`, `pyproject.toml` -- ignore output; add test path.

**Acceptance Criteria:**
- Given resolved demo config, when `make generate PROFILE=demo VOLUME=ci` runs twice, then `find datagen/out -type f | sort | xargs sha256sum` is identical.
- Given generated output, when `make marker-check PATH=datagen/out` runs, then it passes.
- Given generated output, when `make generate-upload` runs, then `gcloud storage ls -r gs://$PROJECT-landing/` lists the member CSV under a path containing its SHA-256 and `select count(*) from mpi_eval.ground_truth` equals the manifest's member count; running it again leaves the count unchanged.
- Given the repo, when `make validate` runs, then it passes (lint, tests, config, phi-scan, marker-check).

## Implementation Notes

- `config/test_load.py` VALID_DEFAULTS gained a `datagen` block (new required schema key).
- Base coverage year is fixed at 2024 (`datagen/generate.py` BASE_YEAR) so output never reads the clock; first-year coverage may start mid-year.
- Upload skip check lists `source=<s>/feed=<f>/**` and matches `/sha256=<sha>/`; a failed `cp` re-checks before erroring (race with an identical upload).
- Makefile `UV` var reuses the PATH= guard for the new targets (the `resolve` prerequisite itself still calls bare uv).

## Plan Change Log

## Review Triage Log

### 2026-10-08 — Review pass
- verdicts: 11 findings — high 0, medium 1, low 7, false 2, maybe-false 0 (one finding split into two rows: quiet flag / atomicity)
- findings:
  - `[medium]` `[patch]` person_code positional, dependents labelled 02 in spouse-less households — fixed: Household.has_spouse, 01/02/03+ by role, test added
  - `[low]` `[patch]` records_per_file cut splits the last household — fixed: stop at household boundary
  - `[low]` `[reject]` names.txt includes names of truncated members; reads ctx._built — moot after household-boundary fix for split members; extra names only widen the scan
  - `[low]` `[reject]` missing config/resolved.yaml gives a traceback — generate/generate-upload depend on resolve, which writes it
  - `[low]` `[defer]` ground-truth delete+load not atomic — rerun recovers; deferred
  - `[false]` `[reject]` bq --quiet after query subcommand may be rejected — live run succeeded with this command line
  - `[false]` `[reject]` ls error masks real error / false match — a failing ls leads to cp, whose failure raises UploadError with stderr; match requires the full /sha256=<64hex>/ segment
  - `[low]` `[defer]` resolve prerequisite not PATH-safe — pre-existing target
  - `[low]` `[patch]` .PHONY lists nonexistent datagen — removed
  - `[low]` `[defer]` --names-file not wired into repo phi-scan (traceback on missing file rejected as low) — deferred until logs/summaries exist
  - `[low]` `[patch]` test gaps (person_code, manifest total vs person_truth) — tests added
  - `[low]` `[patch]` NPI docstring claims no collision — reworded as project convention

## Design Notes

Ground-truth contract (fixed for later entries): `person_truth.jsonl` rows `{"_synthetic", "generator_seed", "source", "source_record_id", "person_truth"}`; `coverage_spans.jsonl` rows `{"_synthetic", "generator_seed", "source", "source_record_id", "coverage_start", "coverage_end"}`; `encounter_claim.jsonl` rows `{"_synthetic", "generator_seed", "source", "encounter_id", "claim_source", "claim_id"}`. Readers skip rows that hold only `_synthetic`. Payer B `source_record_id` = `member_id`; `person_truth` = population `person_id`.

## Verification

**Commands:**
- `make generate PROFILE=demo VOLUME=ci` twice + sha256sum diff -- expected: identical
- `make marker-check PATH=datagen/out` -- expected: 0 findings
- `uv run pytest datagen` -- expected: pass
- `make validate` -- expected: pass
- `make generate-upload` then `gcloud storage ls -r gs://$PROJECT-landing/` and `bq query --use_legacy_sql=false --maximum_bytes_billed=$CAP 'select count(*) from mpi_eval.ground_truth'` -- expected: file listed; count equals member count

## Auto Run Result

Status: built. Implemented the stdlib `datagen/` package (pluggable feed registry, seeded households, Luhn NPI, Payer B member CSV), datagen config keys and schema, manifest + ground-truth contract, `make generate` / `make generate-upload`, and `guardrails.py --names-file`.

Files: `datagen/*` (package, feed, tests), `config/defaults.yaml`, `config/schemas/profile.schema.json`, `config/resolved.yaml`, `config/test_load.py` (test defaults), `tools/guardrails.py`, `tests/test_guardrails.py`, `Makefile`, `.gitignore`, `pyproject.toml`.

Review: 5 patches (1 medium, 4 low), 3 deferred, 4 rejected (reasons in triage log). Follow-up review recommended: false (patched: medium 1, low 4).

Verification: two `make generate PROFILE=demo VOLUME=ci` runs give identical sha256sum; `make marker-check PATH=datagen/out` 0 findings; `make validate` passes; `make generate-upload` landed `payer_b_members_2024.csv` under `sha256=4705e280…` and `select count(*) from mpi_eval.ground_truth` = 4998 = member count.

Residual risks: the pre-fix CSV (`sha256=d1b6…`) stays in the landing bucket (landing is never deleted, AD-3); ci members are 4998, not exactly 5000, because households are never split.
