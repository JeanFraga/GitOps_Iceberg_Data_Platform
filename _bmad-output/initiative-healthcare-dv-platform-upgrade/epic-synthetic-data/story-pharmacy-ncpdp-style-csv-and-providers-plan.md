---
title: 'Pharmacy NCPDP-style CSV and providers'
type: 'feature'
ticket: '4'
created: '2026-10-08'
status: 'built'
baseline_revision: 'beedf62b7f65de82d963f3b4ff791b4b762d99ab'
route: 'full'
route_source: 'auto'
risk: 'low'
review: 'quick'
review_source: 'pinned'
lenses_ran: [quick]
review_loop_iteration: 0
followup_review_recommended: false
context: []
warnings: []
deferred: []
---

<intent-contract>

## Intent

**Problem:** The generator has no pharmacy claims and no provider reference feed, so the Silver pharmacy/provider entities and the NDC 10-to-11 normalization have no source data.

**Approach:** Add two feed modules: `payer_a_pharmacy` (NCPDP-style flat CSV of paid pharmacy claims, NDCs in all three 10-digit hyphenated forms 4-4-2, 5-3-2, 5-4-1) with a shared `datagen/ndc.py` normalizer to 11-digit 5-4-2, and `provider_directory` (practitioners and facilities CSV, NPIs from `datagen.npi.generate_npi`). Each writes marker + manifest entries via the existing registry.

## Boundaries & Constraints

**Always:** Stdlib only; RNG per feed `random.Random(f"{ctx.seed}:{source}:{feed}")`; no wall clock (dates inside `ctx.years`). CSV first line `# <token>`, then header, `lineterminator="\n"`, rows sorted by a stable key. Every file's `records` <= `records_per_file`. Pharmacy members are Payer A members: `claims837.payer_a_member_id(person)` over `ctx.population(records_per_file)`, and each emitted member gets a person_truth row `{"source": "payer_a", "source_record_id": <member id>, "person_truth": <person_id>}` (identical rows dedup in `_jsonl`). Pharmacy key columns per AD-5: payer id, rx_number, fill_number, pharmacy NPI (service_provider_id), date_of_service. Existing feeds' bytes stay unchanged.

**Never:** No real drug names/NDC lookups (NDC labeler/product/package digits are random; drug name is a synthetic label like `SYNTH DRUG 0042`). No noise, drift, samples (entries 6-10). No changes to upload paths or ground_truth schema. Never touch the 837/834/835 RNG streams.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| CI generate | SMALL/ci volume | one `payer_a_pharmacy_<year>.csv` per year and one `providers.csv` | No error expected |
| NDC 4-4-2 | `1234-5678-90` | `01234567890` | — |
| NDC 5-3-2 | `12345-678-90` | `12345067890` | — |
| NDC 5-4-1 | `12345-6789-0` | `12345678900` | — |
| Bad NDC | `123-45-6`, non-digits, 11-digit already-normal | 11-digit `5-4-2` hyphenated or plain 11 digits accepted as-is; anything else raises ValueError | ValueError |

</intent-contract>

## Code Map

- `datagen/registry.py` -- `Feed`, `FeedOutput`, `DataFile`; read-only. Feeds discovered by module name in `datagen/feeds/`.
- `datagen/feeds/payer_b_members.py` -- CSV feed pattern (marker line, csv.writer, sorted rows, per-year files).
- `datagen/claims837.py` -- `payer_a_member_id(person)`, `SOURCE` ("payer_a"); reuse, do not edit.
- `datagen/npi.py` -- `generate_npi(rng)`, `is_valid_npi`; reuse.
- `datagen/generate.py` -- `Context` (`seed`, `volume`, `token`, `years`, `population(n)`, `cache`). No edit expected.
- `datagen/tests/test_datagen.py` -- `test_manifest_shape_and_sha` pins the exact non-834 file list (SMALL = 300 records, 2 years) and `records <= records_per_file`; `test_upload_copies_then_delete_and_load` asserts `len(m["files"]) >= 16` and finds payer_b by index -- update file list for new files.
- `config/standards/guardrails.yaml` -- `.csv` already a data extension; no edit.

## Tasks & Acceptance

**Execution:**
- [x] `datagen/ndc.py` -- `FORMS = ("4-4-2", "5-3-2", "5-4-1")`; `generate_ndc(rng, form) -> str` hyphenated 10-digit; `normalize_ndc(s) -> str` 11 digits (pad the short segment with a leading zero); ValueError otherwise -- shared NDC helper (Silver/Gold reuse).
- [x] `datagen/feeds/payer_a_pharmacy.py` -- `FEED = Feed("payer_a", "pharmacy", ...)`: pool of pharmacies (NPI + NCPDP id `7`+6 digits) and prescribers (NPIs); drug catalog of ~40 NDCs cycling forms so all three appear (product-of-form deterministic, e.g. index % 3); per year one file `payer_a_pharmacy_<year>.csv` with up to `records_per_file` claims; columns: payer_id (`PAYERA`), rx_number, fill_number (0 new, 1+ refills of the same rx), service_provider_id_qualifier (`01` NPI), service_provider_id, ncpdp_id, prescriber_id, cardholder_id (Payer A member id), patient_first_name, patient_last_name, patient_dob (YYYYMMDD), patient_gender_code (1 M / 2 F), date_of_service (YYYYMMDD), product_service_id (hyphenated NDC as sourced), product_name, quantity_dispensed, days_supply, ingredient_cost_paid, dispensing_fee_paid, patient_pay_amount, total_amount_paid, transaction_response_status (`P`); rows sorted by (date_of_service, rx_number, fill_number); person_truth rows for emitted members.
- [x] `datagen/feeds/provider_directory.py` -- `FEED = Feed("provider_directory", "providers", ...)`: one `providers.csv` with practitioners (entity_type_code 1, first/last name, taxonomy code, credential) and facilities (entity_type_code 2, organization name, taxonomy), address, unique NPIs via `generate_npi` (dedupe on collision), count <= records_per_file (e.g. max(10, n//10)); sorted by npi.
- [x] `datagen/tests/test_pharmacy_providers.py` -- at SMALL/ci volume: each of the 3 NDC forms appears in the pharmacy files (regex per form on product_service_id); `normalize_ndc` table for each form plus error cases; every provider NPI passes `is_valid_npi`, unique, both entity types present; pharmacy NPIs valid; every cardholder_id in person_truth payer_a rows; marker on line 1; two runs give identical SHA-256 over all files; existing feed bytes unchanged when the new feeds are excluded (feeds list w/o new modules vs all, compare shared files).
- [x] `datagen/tests/test_datagen.py` -- add the new paths to the pinned list.

**Acceptance Criteria:**
- Given the repo, when `uv run pytest datagen` runs, then all tests pass (NDC forms present, normalization per form, provider NPIs Luhn-valid, two runs same SHA-256).
- Given `make generate PROFILE=demo VOLUME=ci` run twice, when sha256sum over `datagen/out/**` is compared, then identical, and `make marker-check PATH=datagen/out` reports 0 findings.
- Given the repo, when `make validate` runs, then it passes.

## Implementation Notes

- Implemented by subagent; review patches applied in the main session (small direct edits).
- Provider names/addresses reuse population.py lists with the feed's own RNG; they are not added to names.txt.

## Plan Change Log

## Review Triage Log

### 2026-10-08 — Review pass
- verdicts: 4 findings — high 0, medium 0, low 4, false 0, maybe-false 0
- findings:
  - `[low]` `[patch]` copay not capped; total clamped to 0 makes patient_pay + paid != ingredient + fee — fixed: copay = min(copay, ingredient + fee), total unclamped; test asserts the sum
  - `[low]` `[patch]` normalize_ndc `\d` accepts non-ASCII digits — fixed: `[0-9]` patterns; test added
  - `[low]` `[patch]` cardholder test passes on 837/834 payer_a truth rows — fixed: test reads the pharmacy feed's own person_truth
  - `[low]` `[reject]` bytes-unchanged test ignores existing person_truth rows — _jsonl only adds rows (sorted set union); verifying would add test machinery for a defect unlikely in practice

## Design Notes

Assumptions (autonomous): pharmacy belongs to Payer A (PBM-style claims for the same members as 837/834); providers come from a standalone `provider_directory` source because no payer owns the reference feed; provider NPIs are generated independently of 837 billing NPIs (linking providers to encounters is entry 5 / Silver work).

## Verification

**Commands:**
- `uv run pytest datagen` -- expected: pass
- `make generate PROFILE=demo VOLUME=ci` twice + `find datagen/out -type f | sort | xargs sha256sum` diff -- expected: identical
- `make marker-check PATH=datagen/out` -- expected: 0 findings
- `make validate` -- expected: pass

## Auto Run Result

Status: built. Added `datagen/ndc.py` (3 10-digit NDC forms, normalize to 11-digit 5-4-2), `payer_a_pharmacy` NCPDP-style CSV feed (one file per year, all 3 NDC forms, AD-5 key columns, person_truth for emitted members) and `provider_directory` providers CSV (practitioners + facilities, unique Luhn NPIs).

Files: `datagen/ndc.py`, `datagen/feeds/payer_a_pharmacy.py`, `datagen/feeds/provider_directory.py`, `datagen/tests/test_pharmacy_providers.py` (new); `datagen/tests/test_datagen.py` (pinned file list).

Review: 3 patches (low), 0 deferred, 1 rejected (low; reason in triage log). Follow-up review recommended: false (patched: high 0, medium 0, low 3).

Verification: `uv run pytest datagen` 42 passed; two `make generate PROFILE=demo VOLUME=ci` runs identical sha256sum; `make marker-check PATH=datagen/out` 0 findings; `make validate` passed. Not run: `make generate-upload`.

Residual risks: provider NPIs are independent of 837 billing NPIs; provider names not in names.txt for phi-scan.
