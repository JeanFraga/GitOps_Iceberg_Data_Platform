---
title: 'EMR Facility 1 FHIR NDJSON'
type: 'feature'
ticket: '5'
created: '2026-10-08'
status: 'built'
baseline_revision: '2a5bcf4d560711401900db78a0c7d46bfdd06278'
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
      No test ties each Encounter's subject Patient to the NM1*IL member of the claim behind it.
    evidence: |-
      test_patient_truth_matches_837_member checks MRN->person via the PA member id scheme only; a wrong subject reference would pass.
    location: >-
      datagen/tests/test_fhir.py test_patient_truth_matches_837_member
    severity: low
---

<intent-contract>

## Intent

**Problem:** The MPI and Silver/Vault epics need EMR patients and encounters (FR-2: FHIR R4 NDJSON, EMR Facility 1, at least one era) and the generator emits only payer feeds.

**Approach:** Add a shared stdlib FHIR builder plus four feed modules (Patient, Practitioner, Organization, Encounter) under source `emr_facility_1`, one NDJSON file per feed for era `F1`. Encounters are derived from a deterministic sample of original (frequency 1) 837P and 837I claims so they are matchable to claims by patient + date + NPI, carry no claim id, and reuse the 837 `encounter_id` as `Encounter.id` so the existing `encounter_claim` ground-truth rows are the link. Not certified against US Core.

## Boundaries & Constraints

**Always:** Source `emr_facility_1`; feeds `patient`, `practitioner`, `organization`, `encounter`; files `emr_facility_1_<feed>_F1.ndjson` with `era="F1"`; one JSON object per line (`json.dumps(..., separators=(",", ":"))`, keys in insertion order `resourceType`, `id`, `meta`, ...), lines sorted by `id`, trailing `\n`. Every resource has `meta.tag = [{"system": "urn:synthetic-data", "code": <ctx.token>}]` (token within the first 4096 bytes). Encounter references `Patient/<id>`, `Practitioner/<id>` (participant individual), `Organization/<id>` (serviceProvider), all of which exist in the generated files. Practitioner/Organization identifiers use system `http://hl7.org/fhir/sid/us-npi` with the 837 rendering/attending and billing NPIs. Patient identifier MRN system `urn:emr-facility-1:mrn`, MRN `F1M` + digits of `person_id`; `person_truth` row per patient `{"source": "emr_facility_1", "source_record_id": <MRN>, "person_truth": <person_id>}`. RNG `f"{seed}:emr_facility_1:fhir"`; result cached in `ctx.cache` so all four feeds share one build. Encounter count `min(records_per_file, eligible)`. Byte-identical across runs.

**Never:** No claim id (CLM01 or REF*F8 value) anywhere in Encounter (or any FHIR) output. No new `encounter_claim` rows, no ground-truth schema change, no third-party FHIR libs, no noise/drift (entries 6-8), no samples (10), no Condition/Procedure resources, no change to 837 file bytes.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| CI generate | `make generate PROFILE=demo VOLUME=ci` | 4 `.ndjson` files under `landing/emr_facility_1/<feed>/`, manifest era `F1` | No error expected |
| 837I-derived encounter | sampled 837I original | `class.code` `IMP`, `period.start`/`end` from service/discharge dates | No error expected |
| 837P-derived encounter | sampled 837P original | `class.code` `AMB`, `period.start` = service date | No error expected |
| Replacement/void claims | freq 7/8 | never sampled as encounters | No error expected |

</intent-contract>

## Code Map

- `datagen/claims837.py` -- `claims(ctx, kind)` returns cached per-claim facts (`era`, `claim_id`, `freq`, `person`, `billing`=(npi, idx, tin), `svc`, `latest`); add `"encounter_id"` and `"other"`=(npi, idx) to each fact dict (no change to file bytes or RNG call order). `encounter_claim` rows already carry `encounter_id` per claim.
- `datagen/population.py` -- `Household(household_id, members, address, has_spouse)`, `Person(person_id, first_name, last_name, sex, dob)`, `Address(line1, city, state, zip)`; read-only. Map person->address via `ctx.population(records_per_file)`.
- `datagen/registry.py` -- `DataFile(name, content, records, era)`, `Feed`, `FeedOutput`; unchanged.
- `datagen/generate.py` -- writes `landing/<source>/<feed>/<name>`, manifest `era`, dedups truth rows; unchanged.
- `datagen/feeds/payer_a_837p.py` -- 13-line feed pattern to mirror.
- `datagen/tests/test_datagen.py` -- `test_manifest_shape_and_sha` asserts exact sorted non-834 path list; add the four `landing/emr_facility_1/...` paths (they sort before `landing/payer_a`). `test_marker_in_every_data_file` checks `.csv/.jsonl` only.
- `datagen/tests/test_x12.py` -- `test_manifest_eras_and_truth` asserts `encounter_claim` count equals 837 records; stays true.
- `config/standards/guardrails.yaml` -- `.ndjson` already a data extension; read-only.

## Tasks & Acceptance

**Execution:**
- [x] `datagen/claims837.py` -- add `encounter_id` and `other` to facts -- encounters reuse them.
- [x] `datagen/fhir.py` -- `build(ctx) -> dict[str, FeedOutput]` cached at `ctx.cache["fhir"]`: sample original 837P/I facts, emit Patient (identifier MRN, name, gender `male`/`female` from sex M/F, birthDate, address), Practitioner (NPI identifier, name), Organization (NPI identifier, name), Encounter (`status` `finished`, `class` v3-ActCode, `subject`, `participant`, `period`, `serviceProvider`, `identifier` visit number system `urn:emr-facility-1:visit` value = `encounter_id`); patient person_truth rows on the patient output.
- [x] `datagen/feeds/emr_facility_1_{patient,practitioner,organization,encounter}.py` -- `FEED = Feed("emr_facility_1", <feed>, lambda ctx: fhir.build(ctx)[<feed>])`.
- [x] `datagen/tests/test_fhir.py` -- every Encounter reference resolves to a generated Patient/Practitioner/Organization; no claim id from `encounter_claim.jsonl` or the 837 files appears in any FHIR line; every Encounter id has an `encounter_claim` row and the `emr_facility_1` files contain no `claim_id` key; every patient MRN is in person_truth with a person, and that person matches the 837 member's person; every line's `meta.tag` carries the token and token within first 4096 bytes; manifest has 4 files with `era` F1; two runs identical SHA-256.
- [x] `datagen/tests/test_datagen.py` -- extend expected path list.

**Acceptance Criteria:**
- Given the repo, when `uv run pytest datagen` runs, then all tests pass.
- Given `make generate PROFILE=demo VOLUME=ci` run twice, when sha256sum of `datagen/out/**` is compared, then they are identical and `make marker-check PATH=datagen/out` reports 0 findings.
- Given the repo, when `make validate` runs, then it passes.

## Implementation Notes

- Practitioner ids `PR<npi>`, Organization ids `ORG<npi>`; Encounter `identifier` (visit number) last in key order.
- Orchestrator added `test_encounter_class_period_and_originals_only` for the matrix rows (AMB/IMP periods, originals only, unique encounter ids).

## Plan Change Log

## Review Triage Log

### 2026-10-08 — Review pass
- verdicts: 6 findings — high 0, medium 0, low 5, false 1, maybe-false 0
- findings:
  - `[low]` `[patch]` originals-only test cannot catch a sampled 7/8 version — added unique Encounter id assertion (a sampled version shares its original's encounter_id)
  - `[low]` `[defer]` no test ties Encounter subject to the claim's NM1*IL member — deferred; needs 837 per-claim parsing in the test
  - `[low]` `[reject]` no pinned test that 837 bytes are unchanged — RNG call order untouched (read); pinned shas add brittleness for an unlikely regression
  - `[low]` `[reject]` Practitioner/Organization name from first claim on cross-kind NPI collision — 10-digit random NPI collision unlikely; guard adds complexity
  - `[low]` `[reject]` gender maps non-M to female — population emits only M/F; mapping guard is speculative
  - `[false]` `[reject]` plan checkboxes/notes empty — fix is a plan edit; checkboxes and notes updated at finalize

## Design Notes

Reusing the 837 `encounter_id` as `Encounter.id` keeps one id namespace in `encounter_claim` and needs no new truth rows; the id (`EA1P00000001`) is not a claim id. Example line (abbreviated):
```
{"resourceType":"Encounter","id":"EA1P00000007","meta":{"tag":[{"system":"urn:synthetic-data","code":"SYNTHETIC-DATA-NO-REAL-PHI"}]},"status":"finished","class":{"system":"http://terminology.hl7.org/CodeSystem/v3-ActCode","code":"AMB"},"subject":{"reference":"Patient/F1M000123"},...}
```

## Verification

**Commands:**
- `uv run pytest datagen` -- expected: pass
- `make generate PROFILE=demo VOLUME=ci` twice + `find datagen/out -type f | sort | xargs sha256sum` diff -- expected: identical
- `make marker-check PATH=datagen/out` -- expected: 0 findings
- `make validate` -- expected: pass

## Auto Run Result

Status: built. Added EMR Facility 1 FHIR R4 NDJSON (Patient, Practitioner, Organization, Encounter), era F1, built by `datagen/fhir.py` from a sample of original 837P/837I claims; Encounter.id reuses the 837 encounter_id so existing `encounter_claim` rows are the only claim link; marker in every resource's meta.tag; patients in person_truth by MRN.

Files: `datagen/fhir.py` (new builder), `datagen/feeds/emr_facility_1_{patient,practitioner,organization,encounter}.py` (feeds), `datagen/claims837.py` (facts carry encounter_id/other), `datagen/tests/test_fhir.py` (new), `datagen/tests/test_datagen.py` (path list).

Review: 1 patch (low), 1 deferred (low), 4 rejected (reasons in triage log). Follow-up review recommended: false (patched: low 1).

Verification: `uv run pytest datagen` 48 passed; two `make generate PROFILE=demo VOLUME=ci` runs identical sha256; `make marker-check PATH=datagen/out` 0 findings; `make validate` passed. Not run: `make generate-upload`.

Residual risks: not checked against US Core; subject-to-claim-member link only indirectly tested (deferred).
