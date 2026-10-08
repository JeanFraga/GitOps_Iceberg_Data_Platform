---
title: 'Data drift samples in the manifest'
type: 'feature'
ticket: '8'
created: '2026-10-08'
status: 'built'
baseline_revision: 'f2ec48da4549d1861f7392cfc1aeca7eb9bf6346'
route: 'full'
route_source: 'auto'
risk: 'low'
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

**Problem:** FR-36 (generator half) needs four pluggable data-drift scenarios (code-mix, null-rate, unit/scale, amount-distribution shift) applied in the default run and listed in the manifest; today `manifest["data_drift"]` is always `[]`.

**Approach:** New `datagen/data_drift.py` mirrors `datagen/drift.py`: a `SCENARIOS` registry and `apply(ctx, feed, files) -> (files, entries)`, reusing drift.py's `_parse`, `_serialise`, `_Chunk`. For a target feed, the base file (the LAST file whose name does not contain `_drift_`) is split: base keeps the head; each data-drift scenario on that feed takes its own trailing chunk into `<stem>_datadrift_<scenario><ext>` (same era), with the value shift applied. `generate()` calls it after `drift.apply` and fills `manifest["data_drift"]`.

## Boundaries & Constraints

**Always:**
- Scenario names: `code_mix`, `null_rate`, `unit_scale`, `amount_shift`. Target keys: `scenario, source, feed, field, magnitude` plus `codes` (code_mix, non-empty list), `rate` (null_rate, 0<rate<=1), `factor` (unit_scale, amount_shift; >0, !=1). Missing/invalid key, unknown scenario, feed not generated, field missing, unsupported format → `data_drift.DataDriftError(ValueError)` (validated before any feed is written); `__main__` catches it beside `DriftError`.
- Behaviour (whole chunk unless stated; RNG `random.Random(f"{ctx.seed}:data_drift:{source}:{feed}:{scenario}")`):
  - `code_mix`: every value → `rng.choice(codes)`.
  - `null_rate`: each record nulled with probability `rate` (at least one); CSV `""`, NDJSON `null`.
  - `unit_scale`: numeric value × `factor`, formatted as int if the original was int-like else 2 decimals.
  - `amount_shift`: value × `factor` × `rng.uniform(0.9, 1.1)`, 2 decimals.
  Empty / non-numeric originals are left unchanged for the numeric scenarios.
- Default config `datagen.data_drift` in `config/defaults.yaml`, in this order:
  - `code_mix` payer_b/members `sex`, codes `["1","2"]`, magnitude 0.5
  - `null_rate` payer_b/members `pcp_npi`, rate 0.6, magnitude 0.4
  - `unit_scale` payer_a/pharmacy `quantity_dispensed`, factor 1000, magnitude 10
  - `amount_shift` payer_a/pharmacy `total_amount_paid`, factor 1.8, magnitude 0.4
- Magnitude semantics (measured drifted chunk vs base file of same feed and era): code_mix = total variation distance of value distributions; null_rate = null-share difference; unit_scale and amount_shift = |mean_drift/mean_base − 1|. Defaults must exceed their magnitude.
- Split rule identical to drift.py (N base records, m scenarios on the feed, k = max(1, N//10), config order). Manifest entry per scenario in config order: `{scenario, source, feed, file (landing path), field, magnitude, first_affected_record}` (1-based physical line of the first changed record; CSV marker line 1, header 2).
- `Context` gains `data_drift: tuple[dict, ...] = ()`; profile schema gets optional `data_drift` array; regenerate `config/resolved.yaml` with `make resolve`. Byte-identical output across runs; marker kept in every file.

**Never:** No profiling/flagging (epic-silver-normalization), no Gold block, no change to feed modules, noise, population, ground truth, schema-drift behaviour or its existing file bytes, no X12, no samples, no BigQuery, no new deps.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Default CI run | config-driven CI Context | 4 `data_drift` entries, 4 `_datadrift_` files; each stat beats magnitude | No error expected |
| No data drift | Context without `data_drift` | `data_drift == []`, output unchanged | No error expected |
| Coexists with schema drift | pharmacy has 2 schema + 2 data scenarios | schema drift files byte-identical to a run without data drift; record totals preserved | No error expected |
| Bad target | unknown scenario / missing field / missing `codes` / X12 feed | generate raises | `DataDriftError` |

</intent-contract>

## Code Map

- `datagen/drift.py` -- reuse `_parse`, `_serialise`, `_Chunk`, the split arithmetic in `apply`; read-only (import from it).
- `datagen/generate.py` -- `Context` (add field); in `generate()` validate targets alongside `drift.validate` and the generated-feed check; call `data_drift.apply(ctx, feed, drifted)` after `drift.apply`; `manifest["data_drift"]` sorted by config order (pattern: `_order`).
- `datagen/__main__.py` -- pass `tuple(dg.get("data_drift", []))`; catch `DataDriftError`.
- `config/defaults.yaml` `datagen.schema_drift` block; `config/schemas/profile.schema.json` schema_drift definition (copy pattern, `additionalProperties: false` on datagen).
- `datagen/tests/test_drift.py` -- shows config-driven CI context and base-file lookups; base file selection must exclude `_datadrift_` too if it globs.
- `datagen/tests/test_noise.py`, `test_datagen.py` -- adapt only if new files break a glob assumption.

## Tasks & Acceptance

**Execution:**
- [x] `datagen/data_drift.py` -- error, registry, validate, apply.
- [x] `datagen/generate.py`, `datagen/__main__.py` -- wiring, manifest, errors.
- [x] `config/defaults.yaml`, `config/schemas/profile.schema.json`, `config/resolved.yaml` -- four default targets.
- [x] `datagen/tests/test_data_drift.py` -- config-driven CI run: all 4 scenarios in manifest with all keys, files exist in `files[]`; per entry the measured statistic of the drifted file vs the base file of same feed/era exceeds `magnitude`; line at `first_affected_record` changed; records total preserved; matrix rows; two runs identical SHA-256 over output.

**Acceptance Criteria:**
- Given the repo, when `uv run pytest datagen` runs, then all tests pass.
- Given `make generate PROFILE=demo VOLUME=ci` run twice, when sha256 over `datagen/out/**` is compared, then it is identical, the manifest lists the 4 data-drift scenarios, and `make marker-check PATH=datagen/out` reports 0 findings.
- Given the repo, when `make validate` runs, then it passes.

## Implementation Notes

- `generate()` now runs two passes: generate + schema-drift every feed, check data-drift targets (format, field, record count), then write; so a bad target writes nothing.
- `apply` raises `DataDriftError` when a scenario changes no value (guard beyond the plan). NDJSON numeric scenarios keep the original JSON type.
- Files: `datagen/data_drift.py` (new), `datagen/tests/test_data_drift.py` (new), `datagen/generate.py`, `datagen/__main__.py`, `config/defaults.yaml`, `config/schemas/profile.schema.json`, `config/resolved.yaml`.

## Plan Change Log

## Review Triage Log

### 2026-10-08 — Review pass
- verdicts: 7 findings — high 0, medium 0, low 7, false 0, maybe-false 0
- findings:
  - `[low]` `[reject]` repeated scenario on one feed gives colliding file names / `_order` keys — only reachable through deliberate misconfiguration (default has none); same choice as entry 7; a guard adds complexity.
  - `[low]` `[reject]` `null_rate` on already-empty values may change nothing and raise — default `pcp_npi` is always filled; handling it adds branches.
  - `[low]` `[reject]` `first_affected_record` test does not compare against the original value for numeric scenarios — code_mix/null_rate forms (1/2, empty) cannot equal originals (F/M, filled NPI); `_changed` computes the index from a real before/after diff; extra test plumbing adds little.
  - `[low]` `[reject]` coexistence test checks totals, not per-record identity of base + chunks — the split is plain slicing of one line list; totals plus schema-drift byte identity are enough.
  - `[low]` `[reject]` NDJSON field lookup only in the first record — mirrors drift.py (accepted in entry 7); no default NDJSON target.
  - `[low]` `[patch]` plan task boxes and Implementation Notes not filled — filled at finalize.
  - `[low]` `[patch]` profile schema allowed `factor: 1` — added `"not": {"const": 1}` to `data_drift.items.factor`, re-ran `make resolve`/`make validate` (applied in the main session; direct one-line fix).

## Design Notes

Splitting (as in entry 7) keeps every record exactly once in landing; the drifted chunk lands as a later file of the same era, giving E4's profiler a "previous file of same source and era" (the base) to compare against. Data drift picks the non-`_drift_` base so schema-drift chunks stay untouched.

## Verification

**Commands:**
- `uv run pytest datagen` -- expected: pass
- `make generate PROFILE=demo VOLUME=ci` twice + `find datagen/out -type f | sort | xargs sha256sum` diff -- expected: identical
- `make marker-check PATH=datagen/out` -- expected: 0 findings
- `make validate` -- expected: pass

## Auto Run Result

Status: built. Added `datagen/data_drift.py` with four pluggable FR-36 data-drift scenarios (`code_mix`, `null_rate`, `unit_scale`, `amount_shift`). Each target splits the feed's base (non-`_drift_`) file into a trailing `_datadrift_<scenario>` chunk in the same era. The manifest `data_drift` lists scenario, source, feed, file, field, magnitude and first_affected_record. Defaults: members `sex` code mix, members `pcp_npi` null rate, pharmacy `quantity_dispensed` x1000, pharmacy `total_amount_paid` x1.8.

Files: `datagen/data_drift.py` (new module), `datagen/tests/test_data_drift.py` (new tests), `datagen/generate.py` (Context field, two-pass validate-then-write, manifest), `datagen/__main__.py` (config pass-through, error), `config/defaults.yaml` (4 targets), `config/schemas/profile.schema.json` (data_drift schema), `config/resolved.yaml` (regenerated).

Review (quick): 7 low findings; 2 patched (schema `factor != 1`, plan bookkeeping), 5 rejected with reasons in the triage log, 0 deferred. Follow-up review recommended: false (patched: low 2).

Verification: `uv run pytest datagen` 102 passed; `make validate` passed; two `make generate PROFILE=demo VOLUME=ci` runs identical sha256 with 4 data_drift entries; `make marker-check PATH=datagen/out` 0 findings. Not run: `make generate-upload` (no GCP change in this story).

Residual risks: code_mix default is a full code-system swap (TVD 1.0), not a subtle mix; repeated scenario on one feed is unguarded (as in schema drift).
