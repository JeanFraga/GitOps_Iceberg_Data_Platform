---
title: 'Identity noise plugins, edge-case rate and held-out eval seed'
type: 'feature'
ticket: '6'
created: '2026-10-08'
status: 'built'
baseline_revision: '811045692b6e7b83018546b950c770ef75b83bd4'
route: 'full'
route_source: 'auto'
risk: 'medium'
review: 'quick'
review_source: 'pinned'
lenses_ran: [quick]
review_loop_iteration: 1
followup_review_recommended: false
context: []
warnings: [oversized]
deferred: []
---

<intent-contract>

## Intent

**Problem:** FR-4 needs identity noise on member and patient records with a measured 2% ± 0.5 pp edge-case rate and an evaluation seed carrying a noise scenario the training seed lacks; today every feed emits each person's clean identity.

**Approach:** A new `datagen/noise.py` holds a registry of pluggable noise scenarios (one function each, covering the full FR-4 list) and a `view(ctx, source, record_id, person, address)` that deterministically decides, per identity record `(source, source_record_id)`, whether it is noisy and which applicable scenario applies, returning the identity fields the feed writes. Every feed that writes person identity fields uses that view; `person_truth` rows carry `noise_type` (null when clean); the manifest records run kind, rate and scenarios present. A `--eval` generate flag runs with `datagen.eval_seed` and all scenarios; the training run excludes `datagen.eval_only_scenarios`.

## Boundaries & Constraints

**Always:**
- Config keys in `config/defaults.yaml` under `datagen`: `edge_case_rate: 0.02`, `eval_only_scenarios: [twin, cross_payer_switch]`. Read them in `__main__.py`; `Context` gains `edge_case_rate: float = 0.02`, `scenarios: tuple[str, ...]` (default all), `run: str = "train"`.
- Scenario names (exact): `typo`, `nickname`, `name_swap`, `hyphenated_surname`, `dob_day_month_swap`, `twin`, `move`, `ssn_missing`, `ssn_last4`, `ssn_default`, `surname_change`, `newborn_placeholder`, `jr_sr`, `shared_household`, `cross_payer_switch`. Each has an applicability predicate (e.g. `dob_day_month_swap` only when day ≤ 12 and day ≠ month; `newborn_placeholder` only age < 1 at `population.REFERENCE_DATE`; `nickname` only when the first name has a table entry; `cross_payer_switch` only for sources `payer_a`/`payer_b`); `typo` is always applicable, so a selected record always gets a scenario.
- Selection is order-independent: derive a `random.Random` from `f"{ctx.seed}:noise:{source}:{record_id}"`; the record is noisy when its first draw `< q` with `q = 1 - sqrt(1 - edge_case_rate)` (so the share of true-match record pairs with ≥ 1 noisy side ≈ rate); the scenario is then drawn from the applicable, enabled scenarios in registry order. The same `(source, record_id)` gives the same view in every feed (payer_a 834/837/835/pharmacy share member ids).
- SSN: deterministic per person, 9 digits, no dashes, area starting `9` (never a valid SSN), from a hash of `person_id`; emitted only in the Payer B CSV (new last column `ssn`) and the FHIR Patient identifier (system `http://hl7.org/fhir/sid/us-ssn`). `ssn_missing` → empty / identifier omitted; `ssn_last4` → last 4 digits only; `ssn_default` → `999999999`.
- `person_truth` rows gain key `noise_type` (scenario name or `null`); rows stay deduplicated and every member/patient record still maps to exactly one `person_truth`. Upload loads with `--ignore_unknown_values`, so no BigQuery change.
- Manifest gains `"run"` (`train`/`eval`), `"edge_case_rate"`, `"noise_scenarios"` (sorted names actually present in `person_truth`). `names.txt` also contains every noisy full name emitted.
- Same seed, run kind and parameters → byte-identical output across runs; synthetic marker unchanged on every file.

**Never:** No change to population RNG or the per-feed RNG streams' call order (noise uses its own RNG). No new third-party deps. No schema-drift or data-drift work (entries 7-8), no samples (10), no BigQuery DDL. No noise on provider/practitioner/organization records. No SSN with dashes (phi-scan pattern).

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Training run | `python -m datagen generate` | seed `datagen.seed`, `run: train`, no `twin`/`cross_payer_switch` in truth or manifest | No error expected |
| Eval run | `python -m datagen generate --eval` | seed `datagen.eval_seed`, `run: eval`, manifest scenarios ⊋ some scenario absent from train | No error expected |
| Rate 0 | `edge_case_rate=0` | no noisy record; all `noise_type` null | No error expected |
| Unknown eval-only name | config names a non-registry scenario | generate exits 1 with a message naming it | `ValueError` caught in `__main__` |
| Day > 12 DOB | record picks among applicable | never `dob_day_month_swap` | No error expected |

</intent-contract>

## Code Map

- `datagen/generate.py` -- `Context` dataclass (add fields above); `generate()` builds manifest (add keys); `_jsonl` prefixes `_synthetic`, `generator_seed`; names collected from `ctx._built` (also add names noise registers, e.g. `ctx.cache["noise_names"]`).
- `datagen/__main__.py` -- `generate` subcommand: add `--eval`; build scenario set; validate eval-only names.
- `datagen/population.py` -- `Person(person_id, first_name, last_name, sex, dob)`, `Address`, `LAST`, `FIRST_F/M`, `STREETS`, `SUFFIXES`, `CITIES`, `REFERENCE_DATE`; read-only (reuse lists for surname/twin/move picks).
- Identity writers to route through `noise.view` (record id in parentheses): `datagen/feeds/payer_b_members.py` (`member_id`; also add `ssn` column), `datagen/feeds/payer_a_834.py` NM1*IL/N3/N4/DMG (`mid`), `datagen/claims837.py` `_claim` NM1*IL/DMG (`member_id`), `datagen/feeds/payer_a_835.py` NM1*QC (`c["member_id"]`), `datagen/feeds/payer_a_pharmacy.py` patient name/dob (`member`), `datagen/fhir.py` Patient name/birthDate/address/identifier (`mrn(person_id)`). Each of these appends `person_truth`: add `noise_type` from the view.
- `datagen/tests/test_datagen.py`, `test_x12.py`, `test_x12_834_835.py`, `test_pharmacy_providers.py`, `test_fhir.py` -- existing assertions may compare emitted names/dob to population or count columns; adapt only where noise legitimately changes values.
- `config/defaults.yaml` `datagen:` block; regenerate `config/resolved.yaml` via `make resolve` (check-resolved is in `make validate`).
- `Makefile` `generate` target: pass `$(if $(EVAL),--eval)`.
- `config/schemas/profile.schema.json` -- `datagen` properties: add optional `edge_case_rate` (number 0-1) and `eval_only_scenarios` (array of strings), else `make resolve` rejects the keys.
- Address-changing scenarios (`move`, `shared_household`, `cross_payer_switch`) are applicable only for sources whose every record writes an address: `payer_b` and `emr_facility_1` (Payer A 837/835/pharmacy records emit no address, so a `payer_a` address noise would be labelled but invisible). `cross_payer_switch` therefore applies to `payer_b` only. SSN scenarios likewise only `payer_b`/`emr_facility_1`. Every applicable scenario must change at least one field that source writes.
- `shared_household` must set the address to a different existing household's address from the context's built population (deterministic pick via the noise RNG), not a newly invented address; `move` invents a new address. The view therefore needs access to the population's addresses (e.g. pass a pool into the scenario apply).
- Unknown eval-only scenario: raise a dedicated `noise.ScenarioError(ValueError)` and catch only that (plus existing errors) in `__main__.py`; never catch bare `ValueError`.

## Tasks & Acceptance

**Execution:**
- [x] `config/defaults.yaml` (+ `config/resolved.yaml` via `make resolve`) -- add `edge_case_rate`, `eval_only_scenarios`.
- [x] `datagen/noise.py` -- scenario registry, applicability, `ssn(person_id)`, `view(...)` returning a frozen `Identity(first_name, last_name, dob, sex, address, ssn, noise_type)`; cached per `(source, record_id)` in `ctx.cache`.
- [x] `datagen/generate.py`, `datagen/__main__.py`, `Makefile` -- context fields, `--eval`, manifest keys, names.
- [x] Six identity writers listed in the Code Map -- use the view and record `noise_type`.
- [x] `datagen/tests/test_noise.py` -- at CI volume for the training and eval runs: every `person_truth` row has one person and `noise_type` in registry or null, and every member/patient record id appearing in the landing files has a truth row; measured share of true-match pairs (distinct records grouped by `person_truth`, all within-person pairs) with ≥ 1 noisy side in [0.015, 0.025] for both seeds; eval manifest `noise_scenarios` contains a name absent from training's; training contains no eval-only scenario; two runs identical SHA-256; every scenario function unit-tested on a fixed person (incl. matrix rows: rate 0, day > 12, unknown eval-only name).
- [x] Existing tests -- adapt for noise only.

**Acceptance Criteria:**
- Given the repo, when `uv run pytest datagen` runs, then all tests pass.
- Given `make generate PROFILE=demo VOLUME=ci` and `make generate PROFILE=demo VOLUME=ci EVAL=1`, when each is run twice, then each pair has identical sha256 over `datagen/out/**`, and `make marker-check PATH=datagen/out` reports 0 findings.
- Given the repo, when `make validate` runs, then it passes.

## Implementation Notes

## Plan Change Log

### 2026-10-08 — loop 1
- Trigger: review found `shared_household` invented an address (same as `move`) despite Design Notes; address noise labelled on Payer A records that emit no address (invisible noise inflating the measured rate); `__main__` caught bare `ValueError`.
- Amended: Code Map bullets on address-scenario applicability, `shared_household` using an existing household address, `ScenarioError`, and the profile schema.
- Avoids: noise_type labels with no observable change; two scenario labels with identical behaviour; masking internal ValueErrors.
- KEEP: the first attempt's design otherwise worked and passed all checks (62 tests, identical train/eval sha256, validate): `noise.py` registry with `Identity`, `ssn()`, `decide()` with per-record RNG `f"{seed}:noise:{source}:{record_id}"` and q = 1-sqrt(1-rate), `view()` cache in `ctx.cache["noise_views"]`, noisy names in `names.txt`, feed wiring in the six writers with `noise_type` on person_truth, Payer B `ssn` last column, FHIR `us-ssn` identifier omitted when missing, `--eval` flag, manifest keys, `test_noise.py` coverage (truth rows, pair-rate band both runs, train/eval scenario sets, determinism, rate 0, unknown name, day > 12, per-scenario units).

## Review Triage Log

### 2026-10-08 — Review pass
- verdicts: 5 findings — high 0, medium 2, low 3, false 0, maybe-false 0
- findings:
  - `[medium]` `[bad_plan]` `shared_household` invents an address like `move` — Code Map amended: pick another existing household's address.
  - `[medium]` `[bad_plan]` address scenarios labelled on Payer A records that never emit an address — Code Map amended: address scenarios only for `payer_b`/`emr_facility_1`.
  - `[low]` `[bad_plan]` `__main__` catches bare `ValueError` — Code Map amended: dedicated `ScenarioError`.
  - `[low]` `[reject]` `_address_of` rebuilds lookup on every miss — every viewed person comes from the built population, so misses do not occur in practice; guard adds complexity.
  - `[low]` `[reject]` existing tests not adapted / no Payer B header check — existing tests still pass unchanged; plan only required adapting where noise changed values.

### 2026-10-08 — Review pass (loop 1 re-derivation)
- verdicts: 3 findings — high 0, medium 0, low 2, false 1, maybe-false 0
- findings:
  - `[low]` `[patch]` dead `NICKNAMES["Benjamin"]` entry (not a population name; its nickname `Ben` is a real first name) — entry deleted by the orchestrator (one-line deletion).
  - `[low]` `[reject]` `Context` defaults label `run="train"` with all scenarios for direct callers — defaults are as the plan prescribes; only the CLI is a run surface and it applies the exclusion; changing it means editing the plan.
  - `[false]` `[reject]` plan file in diff says `in-progress` vs disk `in-review` — the workflow moves plan status between diff staging and review; not a code defect.

## Design Notes

Pair-rate math: with per-record probability q, a within-person pair is clean with prob (1-q)², so q = 1 - √(1-r) ≈ 0.01005 for r = 0.02. Scenarios are record transforms of identity fields (assumption, autonomous): `twin` replaces the first name with a different same-sex name keeping DOB/surname/address (sibling confusion); `shared_household` gives the address of another household; `cross_payer_switch` gives a moved address plus `surname_change`-style surname (identity drift between payers); `jr_sr` appends ` JR`/` SR` to the surname; `newborn_placeholder` sets first name `BABY BOY`/`BABY GIRL`.

## Verification

**Commands:**
- `uv run pytest datagen` -- expected: pass
- `make generate PROFILE=demo VOLUME=ci` (and with `EVAL=1`) twice each + `find datagen/out -type f | sort | xargs sha256sum` diff -- expected: identical
- `make marker-check PATH=datagen/out` -- expected: 0 findings
- `make validate` -- expected: pass

## Auto Run Result

Status: built. Added `datagen/noise.py` (15 pluggable FR-4 identity-noise scenarios, per-record order-independent selection with q = 1-sqrt(1-rate), deterministic 9xx SSNs), wired the six identity writers (Payer B CSV + new `ssn` column, 834, 837, 835, pharmacy, FHIR Patient + us-ssn identifier) through the noise view, `noise_type` on every `person_truth` row, manifest `run`/`edge_case_rate`/`noise_scenarios`, `--eval` (`make generate EVAL=1`) using `datagen.eval_seed` and all scenarios while training excludes `datagen.eval_only_scenarios` (`twin`, `cross_payer_switch`).

Files: `datagen/noise.py` (new), `datagen/tests/test_noise.py` (new), `datagen/generate.py`, `datagen/__main__.py`, `datagen/claims837.py`, `datagen/fhir.py`, `datagen/feeds/payer_{a_834,a_835,a_pharmacy,b_members}.py`, `config/defaults.yaml`, `config/resolved.yaml`, `config/schemas/profile.schema.json`, `Makefile`.

Review: pass 1 — 3 bad_plan (shared_household invented address, invisible Payer A address noise, bare ValueError catch) → plan amended, code re-derived; 2 low rejected. Pass 2 — 1 low patched (dead nickname entry), 1 low rejected, 1 false. Follow-up review recommended: false (patched: low 1).

Verification: `uv run pytest datagen` 75 passed; train and eval `make generate PROFILE=demo VOLUME=ci` each twice with identical sha256; `make marker-check PATH=datagen/out` 0 findings; `make validate` passed. Train manifest 13 scenarios (no twin/cross_payer_switch), eval 15. Not run: `make generate-upload` (person_truth `noise_type` is loaded with `--ignore_unknown_values`; the BigQuery table has no such column yet).

Residual risks: pair-rate band holds for the two configured seeds at CI volume; other seeds/volumes could fall just outside. Scenario semantics (twin, cross_payer_switch, jr_sr males only, surname scenarios 18+) are autonomous assumptions.
