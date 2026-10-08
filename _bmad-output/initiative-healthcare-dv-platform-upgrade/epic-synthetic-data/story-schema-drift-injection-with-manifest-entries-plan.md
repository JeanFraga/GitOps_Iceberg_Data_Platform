---
title: 'Schema drift injection with manifest entries'
type: 'feature'
ticket: '7'
created: '2026-10-08'
status: 'built'
baseline_revision: '971da8b4c6d52f789c08c3875c5aa7f32295d2d4'
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
deferred: []
---

<intent-contract>

## Intent

**Problem:** FR-3 needs five pluggable schema-drift scenarios (rename, add column mid-era, remove column, date format change, cast failure) injected by default and listed in the manifest with scenario, source, file and first affected record; today `manifest["schema_drift"]` is always `[]`.

**Approach:** A new `datagen/drift.py` holds a registry of five scenario functions and `apply(ctx, feed, files) -> (files, entries)`. Configured targets (`datagen.schema_drift` in config) name scenario, source, feed and field. For a target feed, the last file (latest era) is split: the base file keeps the head of its records; each scenario targeting that feed takes its own trailing chunk into a new file `<stem>_drift_<scenario><ext>` in the same era, with the drift applied. `generate()` calls `apply` per feed and fills `manifest["schema_drift"]`.

## Boundaries & Constraints

**Always:**
- Scenario names (exact): `rename_column`, `add_column`, `remove_column`, `date_format`, `cast_failure`. Supported formats: CSV (`.csv`; leading `# <token>` marker line, then header, then one record per line) and NDJSON (`.ndjson`; one JSON object per line, top-level keys). Unsupported format, unknown scenario, target feed not generated, or field missing (CSV header / first JSON record; for `add_column` the field must NOT already exist) → `drift.DriftError(ValueError)`; `__main__` catches it beside `ScenarioError`.
- Default config (`config/defaults.yaml` `datagen.schema_drift`, list of `{scenario, source, feed, field[, to]}`), in this order:
  - `rename_column` payer_b/members `dob` → `to: birth_date` (header name only)
  - `add_column` payer_a/pharmacy `prior_auth_number` (appended last; value `PA` + 8 digits from the drift RNG)
  - `cast_failure` payer_a/pharmacy `quantity_dispensed` (value `N/A`)
  - `remove_column` provider_directory/providers `credential`
  - `date_format` emr_facility_1/patient `birthDate` (`YYYY-MM-DD` → `MM/DD/YYYY`)
- Split: N = data records of the target file, m = scenarios on that feed, k = max(1, N // 10); scenario i (config order, 0-based) takes records [N-(m-i)*k, N-(m-i-1)*k); base keeps [0, N-m*k). Marker line and header (CSV) are kept in every file; DataFile `records` and `era` set correctly (drifted file inherits the base file's era). File name: `payer_b_members_2024.csv` → `payer_b_members_2024_drift_rename_column.csv`.
- `rename_column`, `add_column`, `remove_column`, `date_format` affect every record of their chunk; `cast_failure` affects a deterministic subset (at least one, roughly 1 in 5) chosen with `random.Random(f"{ctx.seed}:drift:{source}:{feed}:{scenario}")`.
- Manifest entry per applied scenario, in config order: `{"scenario", "source", "feed", "file" (landing path, same as `files[].path`), "field", "first_affected_record"}` where `first_affected_record` is the 1-based physical line number in the drifted file of the first record showing the drift (CSV: marker line 1, header 2, so a whole-chunk scenario gives 3).
- `Context` gains `schema_drift: tuple[dict, ...] = ()`; `__main__` passes the config list. Profile schema gets the optional `schema_drift` array. Regenerate `config/resolved.yaml` via `make resolve`.
- Byte-identical output across runs; the synthetic marker stays in every file (FHIR `meta` is never removed or renamed).

**Never:** No change to feed modules, noise, population or ground truth (records only move between files; `person_truth`/`coverage_spans`/`encounter_claim` unchanged). No X12 drift. No data drift (entry 8), no samples (entry 10), no BigQuery change, no third-party deps, no change to `config/fingerprint.py`.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Default CI run | `make generate PROFILE=demo VOLUME=ci` | 5 manifest `schema_drift` entries, 5 extra `_drift_` files | No error expected |
| Direct `Context` without drift | existing tests | output identical to before; `schema_drift == []` | No error expected |
| Two scenarios on one feed | pharmacy add + cast | two drifted files, disjoint chunks, base shrinks by 2k | No error expected |
| Bad target | unknown scenario / missing field / X12 feed | generate exits 1 naming it | `DriftError` |

</intent-contract>

## Code Map

- `datagen/generate.py` -- `Context` dataclass (add `schema_drift`); `generate()` loop: after `result = feed.generate(ctx)` replace `result.files` via `drift.apply(ctx, feed, result.files)` before writing; collect entries, set `manifest["schema_drift"]`. Validate every target's (source, feed) was generated, else `DriftError`.
- `datagen/__main__.py` -- pass `tuple(dg.get("schema_drift", []))`; catch `drift.DriftError`.
- `datagen/registry.py` -- `DataFile(name, content, records, era)` frozen; unchanged.
- `datagen/feeds/payer_b_members.py`, `payer_a_pharmacy.py`, `provider_directory.py` -- CSV: first line `# <token>\n`, then header, `lineterminator="\n"`, no embedded newlines; read-only. `emr_facility_1_patient.py` via `datagen/fhir.py` -- NDJSON, one object per line, compact separators, insertion order; read-only (re-serialise drifted lines with `json.dumps(obj, separators=(",", ":"))`, keeping key order; renamed key keeps its position).
- `config/fingerprint.py` -- `fingerprint(text, "csv"|"jsonl")`; CSV takes the FIRST row, so tests strip the leading `# ` marker line before fingerprinting (the Bronze loader is expected to drop that comment line; assumption).
- `config/defaults.yaml` `datagen:` block; `config/schemas/profile.schema.json` `datagen.properties` (additionalProperties false).
- `datagen/tests/test_datagen.py` -- `test_manifest_shape_and_sha` asserts `schema_drift == []` with a drift-less `Context`; stays true.
- `datagen/tests/test_noise.py` -- module fixture `DG = config.load()["datagen"]` shows how to build a config-driven CI context; tests pick `next(glob('*.csv'))` / `next(glob('*.ndjson'))` (unordered); those only use drift-less contexts today, but if any is switched to a config-driven context, make it select the base file by name.

## Tasks & Acceptance

**Execution:**
- [x] `datagen/drift.py` -- `DriftError`, `SCENARIOS` registry (one function per scenario), `apply(ctx, feed, files)` returning new file list and manifest entries per the split rule.
- [x] `datagen/generate.py`, `datagen/__main__.py` -- context field, wiring, manifest, error handling.
- [x] `config/defaults.yaml`, `config/schemas/profile.schema.json`, `config/resolved.yaml` (`make resolve`) -- default five targets.
- [x] `datagen/tests/test_drift.py` -- with a config-driven CI context (`config.load()["datagen"]`, `volume_profiles.ci`): manifest lists all 5 scenarios with source/feed/file/field/first_affected_record and every `file` exists in `files[]`; for each entry the line at `first_affected_record` shows the drift (renamed header present/old absent for rename; extra value for add; column count reduced for remove; `MM/DD/YYYY` in `birthDate` for date_format; `N/A` that fails `int()` for cast_failure) and lines before it in the chunk (cast_failure) do not; fingerprint of the rename/add/remove drifted files (marker line stripped) differs from the base file of the same era, and date_format/cast_failure keep the base fingerprint; records across base + drifted files equal the undrifted total and `person_truth` is unchanged vs a drift-less run; matrix rows (no drift → `[]`, two scenarios one feed disjoint chunks, `DriftError` for unknown scenario, missing field, X12 target, `add_column` of existing field); two runs identical SHA-256.
- [x] Existing tests -- adapt only where drifted files break a glob assumption.

**Acceptance Criteria:**
- Given the repo, when `uv run pytest datagen` runs, then all tests pass.
- Given `make generate PROFILE=demo VOLUME=ci` run twice, when sha256 over `datagen/out/**` is compared, then it is identical, the manifest lists the 5 scenarios, and `make marker-check PATH=datagen/out` reports 0 findings.
- Given the repo, when `make validate` runs, then it passes.

## Implementation Notes

- Extra `DriftError` cases beyond the plan: `date_format` chunk with no ISO date, file with too few records for its scenarios, `rename_column` without `to` (checked in `validate()` before any feed is written).
- Drifted chunks are re-serialised (`csv.writer` / compact `json.dumps`); base files keep their original bytes.

## Plan Change Log

## Review Triage Log

### 2026-10-08 — Review pass
- verdicts: 8 findings — high 0, medium 0, low 8, false 0, maybe-false 0
- findings:
  - `[low]` `[reject]` no guard against drifting FHIR `meta` (marker) via config — only a deliberate misconfiguration reaches it; marker-check would catch it; guard adds complexity.
  - `[low]` `[patch]` missing `to` for rename caught only after earlier feeds were written — check moved into `validate()`.
  - `[low]` `[reject]` `files[-1]` assumed latest era — every feed appends files in year order; sorting guard adds complexity.
  - `[low]` `[patch]` test `_base` picked earliest era under multi-year volumes — base path now derived from the drifted file name.
  - `[low]` `[reject]` NDJSON missing-field and date_format no-ISO paths untested — simple branches; extra tests add little.
  - `[low]` `[reject]` `ctx_out` global test scaffolding fragile — works for the tested paths; rewrite is churn.
  - `[low]` `[patch]` dead `_Chunk.has` — deleted.
  - `[low]` `[reject]` duplicate (source, feed, scenario) targets overwrite each other — default config has none; rejecting them adds a guard.

## Design Notes

Splitting instead of copying keeps every record exactly once in landing (no duplicate claims or coverage rows) and makes "add column mid-era" literal: the era's later file carries the extra column. AD-5 treats the add file as an additive-only superset of the era (maps to it with a drift_report row); rename/remove land in `unmapped_<fp8>`; date_format/cast_failure keep the era fingerprint and surface as cast failures in Silver (FR-11). Line-ordinal convention matches AD-6 `_line_ordinal` as physical line (assumption).

## Verification

**Commands:**
- `uv run pytest datagen` -- expected: pass
- `make generate PROFILE=demo VOLUME=ci` twice + `find datagen/out -type f | sort | xargs sha256sum` diff -- expected: identical
- `make marker-check PATH=datagen/out` -- expected: 0 findings
- `make validate` -- expected: pass

## Auto Run Result

Status: built. Added `datagen/drift.py` with five pluggable FR-3 schema-drift scenarios (`rename_column`, `add_column`, `remove_column`, `date_format`, `cast_failure`) for CSV and NDJSON. Each configured target splits the feed's latest file into a base plus a trailing `_drift_<scenario>` chunk in the same era. The manifest `schema_drift` lists scenario, source, feed, file, field and first_affected_record (the physical line number). Defaults live in `config/defaults.yaml` `datagen.schema_drift`.

Files: `datagen/drift.py` (new), `datagen/tests/test_drift.py` (new), `datagen/generate.py` (Context field, wiring, manifest), `datagen/__main__.py` (config pass-through, DriftError), `config/defaults.yaml`, `config/schemas/profile.schema.json`, `config/resolved.yaml`.

Review (quick): 3 low findings patched (rename `to` check moved to validate, dead code removed, test base-file lookup fixed); 5 low findings rejected, with reasons in the triage log; 0 deferred. Follow-up review recommended: false (patched: low 3).

Verification: `uv run pytest datagen` 87 passed. Two `make generate PROFILE=demo VOLUME=ci` runs gave identical sha256, with 5 manifest drift entries. `make marker-check PATH=datagen/out` found 0 findings. `make validate` passed. Not run: `make generate-upload`.

Residual risks: the fingerprint comparison assumes the Bronze loader drops the leading `# <token>` CSV marker line, because `config/fingerprint.py` reads the first row as the header. The line-ordinal convention (physical line, 1-based) is an assumption to align with AD-6.
