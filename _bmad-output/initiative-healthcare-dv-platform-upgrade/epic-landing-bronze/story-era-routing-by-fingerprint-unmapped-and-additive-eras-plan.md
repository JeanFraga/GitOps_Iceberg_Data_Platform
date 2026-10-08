---
title: 'Era routing by fingerprint, unmapped and additive eras'
type: 'feature'
ticket: '3'
created: '2026-10-08'
status: 'built'
baseline_revision: 'c28defb4503a951223b7597c9b1f49247dcb7a7e'
route: 'full'
route_source: 'auto'
risk: 'medium'
review: 'quick'
review_source: 'pinned'
lenses_ran: ['quick']
review_loop_iteration: 0
followup_review_recommended: false
context: ['{project-root}/_bmad-output/initiative-healthcare-dv-platform-upgrade/epic-landing-bronze/epic-landing-bronze.md']
warnings: []
deferred:
  - summary: >-
      Additive ALTER TABLE ADD COLUMNS runs before the reconcile gate, so a quarantined additive file still widens main's schema.
    evidence: |-
      Iceberg schema is table-level, not branch-level. ensure_table runs before write_branch. Only empty NULL columns become visible; no rows are published.
    location: >-
      ingestion/bronze.py ensure_table
    severity: low
  - summary: >-
      The x12 fingerprint of payer_a 834 depends on optional segments in the first transaction, so one schema yields two eras (era_2024, era_2024_v2).
    evidence: |-
      Implementation Notes for 3.3. The fix belongs in config/fingerprint.py x12_layout (E1-owned); the owner should confirm the era naming.
    location: >-
      config/fingerprint.py, config/eras/payer_a.yaml
    severity: medium
---

<intent-contract>

## Intent

**Problem:** The loader writes every file to `<feed>__era_2024` (`FIXED_ERA` in `ingestion/__main__.py`), so drifted files land in the wrong era and nothing records drift (AD-5).

**Approach:** Add the era registry `config/eras/<source>.yaml`, validated by `make validate-config`. A new `ingestion/eras.py` resolves (source, feed, fingerprint, columns) to a known era, an additive era or `unmapped_<fp8>`. The loader routes on that result and writes `ops.drift_report` rows for the additive and unmapped cases.

## Boundaries & Constraints

**Always:** Fingerprints come only from `config/fingerprint.py` (AD-22). Each registry entry is `feed -> era -> {fingerprint, columns}`, and era names match `^[a-z0-9_]+$`. One fingerprint maps to at most one era per (source, feed). Seed the registry from the non-drift committed samples only. The payer_b members era is `era_2024`, so 3.1's `members__era_2024` and 3.2's `members__era_2024_wap` keep their names. Keep 3.2's WAP order: drift_report rows are written only after `reconciled`, and never on a skip. Keep `_landed_sha256` and avoid BigQuery reserved prefixes in any new column. `fp8` is lowercase hex.

**Never:** Inferring an era from dates or file names. Editing `fingerprint.py`, `lifecycle.yaml` or the `ops.*` DDL (E1). Adding lifecycle states. Silver padding or `UNMAPPED_ERA` quarantine (E4). Re-appending rows on recovery.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Known fingerprint | `payer_b_members_2024.csv` | `members__era_2024`, no drift row | No error expected |
| Additive superset | `payer_a_pharmacy_2024_drift_add_column.csv` (+`prior_auth_number`) | `pharmacy__era_2024`, new column added to the Iceberg schema, drift row `drift_kind=additive_columns` with the added columns in `detail` | No error expected |
| Rename drift | `payer_b_members_2024_drift_rename_column.csv` (`dob`→`birth_date`) | `members__unmapped_<fp8>`, drift row `drift_kind=unmapped_era` | No error; exit 0 |
| Removed column | `providers_drift_remove_column.csv` (no `credential`) | `providers__unmapped_<fp8>`, `unmapped_era` drift row | No error; exit 0 |
| Column reorder | Same column set as a mapped era, different order | `unmapped_<fp8>`, `unmapped_era` drift row | No error; exit 0 |
| Uppercase era | Registry era `Era_2024` | `make validate-config` fails and names the file and key | ConfigError, nonzero exit |
| Ambiguous superset | Superset of two mapped eras | Map to the era with the most columns; if two tie, `unmapped_<fp8>` | No error |

</intent-contract>

## Code Map

- `ingestion/__main__.py` -- `FIXED_ERA` and the table naming in `load()`; the routing call replaces them
- `ingestion/bronze.py` -- `ensure_table`; additive columns need `ALTER TABLE ADD COLUMN`
- `ingestion/lifecycle.py` -- the bq insert pattern that the drift_report writer copies
- `config/load.py` -- `validate_standards` and `--validate-only`; the registry check is added here
- `config/fingerprint.py` -- `fingerprint`, `fp8`, `csv_layout` (used read-only)
- `infra/modules/bq_ops/schemas/ops.drift_report.json` -- the row shape (`schema_era`, `drift_kind`, `detail`, `mode`)
- `datagen/samples/` -- registry seeds; `manifest.json` era labels (A1, A2, F1, null)

## Tasks & Acceptance

**Execution:**
- [x] `config/eras/{payer_a,payer_b,provider_directory,emr_facility_1}.yaml` -- seed one era per distinct non-drift layout. CSV feeds use `era_2024`; X12 and JSONL use lowercased manifest labels (`a1`, `a2`, `f1`). Fingerprints and columns come from `fingerprint.py` -- the registry is the single source of truth. If two manifest labels share one fingerprint (e.g. 835 a1/a2), seed only the first label as the era and list the other under that era's `aliases`. Do not create two eras with one fingerprint.
- [x] `config/schemas/eras.schema.json` and `config/load.py` -- validate the schema (era pattern, required fields, 64-hex fingerprint) and check that no fingerprint repeats within a feed, from `validate_standards`. This puts the check under `make validate-config`.
- [x] `ingestion/eras.py` (new) -- `resolve(source, feed, fp, columns) -> Route(era, kind, added)`; kind is `known`, `additive` or `unmapped`.
- [x] `ingestion/drift.py` (new) -- write an `ops.drift_report` row with `mode=report_only` and `schema_era` set to the routed era.
- [x] `ingestion/__main__.py`, `ingestion/bronze.py` -- route via `eras.resolve`, evolve the schema on additive, write the drift row after `reconciled`, and remove `FIXED_ERA`.
- [x] `ingestion/tests/test_eras.py`, `config/tests/` -- cover each matrix row on the committed samples, plus every non-drift and datadrift sample resolving to its mapped era.

**Acceptance Criteria:**
- Given every non-drift sample, when its fingerprint is computed, then it matches its registry entry exactly.
- Given a reload of an additive or unmapped file that was skipped as already appended, when the loader runs, then no second drift_report row is written.
- Given the existing demo tables, when payer_b members is routed, then the table is `members__era_2024`.

## Implementation Notes

- payer_a 834 has no manifest era label and two distinct X12 layouts across the samples (data-dependent optional segments in the first ST..SE). Both are seeded as `era_2024` and `era_2024_v2` so no non-drift sample routes to unmapped.
- 835/837 A1 and A2 share a fingerprint per feed, so they are seeded as `a1` with `aliases: [a2]`.
- The registry check skips sources without a file. The repo registry is validated from `validate_standards`, so it runs under `--validate-only`.
- `ensure_table` runs `ALTER TABLE ADD COLUMNS` for new header columns. `write_branch` projects the frame onto the table's columns and writes NULL for columns missing from a narrower file.
- Drift rows are written after `reconciled`, including on the `published_without_reconciled` recovery path, which writes no row data. A crash between `reconciled` and the drift insert loses that drift row, because a reload is skipped.

## Plan Change Log

## Review Triage Log

### 2026-10-08 — Review pass
- verdicts: 6 findings — high 0, medium 3, low 3, false 0, maybe-false 0
- findings:
  - `medium` `patch` After a registry rebind, a reload re-appended into the new era table. Fixed: the skip checks all `<feed>__*` tables for the run's suffix; test added.
  - `medium` `defer` ADD COLUMNS before the gate widens main's schema even when the file is quarantined. Iceberg schema is table-level; only empty columns are exposed.
  - `medium` `patch` Non-CSV files were silently misrouted as CSV. Fixed: refused with UnsupportedFormat, exit 5, until entry 5.
  - `low` `patch` Alias clashes were not validated. Fixed in validate_eras; test added.
  - `low` `patch` A pure column reorder was untested. Case added.
  - `low` `reject` The drift row on crash recovery uses the current registry route. The plan already accepts losing that row; low impact, and the fix would add complexity.

## Auto Run Result

- Summary: the era registry is in config/eras/*.yaml, validated by schema plus validate_eras. The loader routes by fingerprint to a known era, an additive superset (widening the table, with a drift_report row), or unmapped_<fp8> (with a drift_report row), all after reconciled.
- Files: config/eras/*.yaml, config/schemas/eras.schema.json, config/load.py, ingestion/eras.py, ingestion/drift.py, ingestion/__main__.py, ingestion/bronze.py, tests.
- Review: 4 patched (2 medium, 2 low), 2 deferred, 1 rejected.
- Follow-up review recommended: false (no high patched; 2 medium patches are small and covered by tests).
- Verification: pytest ingestion pipeline config gave 130 passed. make validate passed. The uppercase era name was rejected by validate-config.
- Residual risk: column add and NULL-fill are untested on live BigLake REST. The runtime-sa IAM grant is still unapplied.

## Design Notes

**Reorder decision:** AD-22 fingerprints the ordered header, so a reorder is a new fingerprint. "Additive-only superset" means the mapped era's columns appear in the new header in the same relative order, plus at least one extra column. A reorder adds nothing and breaks that order, so it goes to `unmapped_<fp8>`. This is conservative, and recovery is a registry binding (AD-5). Datadrift samples keep their header, so they route as known.

## Verification

**Commands:**
- `uv run pytest ingestion config` -- expected: all pass, including the matrix tests
- `make validate` -- expected: pass; with an uppercase era name in a scratch registry, `make validate-config` exits nonzero
