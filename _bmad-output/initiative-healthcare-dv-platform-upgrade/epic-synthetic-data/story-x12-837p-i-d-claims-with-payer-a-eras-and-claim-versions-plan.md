---
title: 'X12 837P/I/D claims with Payer A eras and claim versions'
type: 'feature'
ticket: '2'
created: '2026-10-08'
status: 'built'
baseline_revision: '7683a74325ad706631502133a684480187839856'
route: 'full'
route_source: 'auto'
risk: 'high'
review: 'quick'
review_source: 'pinned'
lenses_ran: [quick]
review_loop_iteration: 0
followup_review_recommended: false
context: []
warnings: [oversized]
deferred:
  - summary: >-
      Ground-truth writer now drops exact duplicate rows for every table and feed, which could hide a future duplicate-generation bug.
    evidence: |-
      datagen/generate.py _jsonl dedups so Payer A members emitted by 837P/I/D collapse; a per-source dedup or a per-feed no-duplicates assertion would be stricter.
    location: >-
      datagen/generate.py _jsonl
    severity: low
---

<intent-contract>

## Intent

**Problem:** Downstream epics need Payer A professional, institutional and dental claims in X12 005010 shape, with two eras inside the window and original/replacement/void versions, and the generator only has the Payer B CSV feed.

**Approach:** Add a minimal stdlib X12 writer plus three feed modules (837P X222A1, 837I X223A2, 837D X224A2), one file per feed per era, with claim frequency codes 1/7/8, Luhn NPIs from `datagen/npi.py`, ICD-10/HCPCS codes and code-shaped CPT/CDT; the manifest records each file's era. Not certified against the implementation guides.

## Boundaries & Constraints

**Always:** Delimiters: element `*`, component `:` (ISA16), repetition `^`, segment terminator `~` followed by `\n`. ISA is fixed-width (106 chars incl. terminator). Each file: one ISA/IEA, one GS/GE, several ST/SE (at most 500 claims per ST); IEA01 = GS count, GE01 = ST count, SE01 = segment count ST..SE inclusive, control numbers match. Every ST has `BHT*0019*00*<marker token>*...` so the token sits within the first 4096 bytes. Interchange/BHT dates derive from the file's data (no wall clock). Same seed + volume gives byte-identical output; RNG seeded per feed as `f"{seed}:{source}:{feed}"`. Files use extension `.837`. Era boundary 2024-07-01 (era `A1` before, `A2` on/after, to the end of the last year), so a 1-year CI run holds both eras. CPT/CDT values are random code-shaped strings (CPT 5 digits, CDT `D`+4 digits), never real descriptors. Ground-truth contract from entry 1 is unchanged.

**Never:** No third-party X12 or data libraries. No 834/835 (entry 3), noise/drift (6-8), samples (10). No change to upload paths or `mpi_eval.ground_truth` schema. No code descriptors anywhere.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| CI generate | `make generate PROFILE=demo VOLUME=ci` | 6 `.837` files (P/I/D x A1/A2) in manifest, each with `era` | No error expected |
| Replacement / void | claim with frequency 7 or 8 | `CLM05-3` = 7/8 and `REF*F8*<original CLM01>`; original appears earlier in the same feed | No error expected |
| 837I | every 837I claim | type of bill (CLM05 `<2 digits>:A:<freq>`), DTP*435 admit, DTP*096 discharge, `SV2` revenue codes, `HI*DR:` DRG | No error expected |
| Round-trip parse | any generated file | parser splits into segments; counts in SE/GE/IEA match | test fails on mismatch |

</intent-contract>

## Code Map

- `datagen/registry.py` -- `DataFile(name, content, records)`: add optional `era: str | None = None`. `Feed`/`discover()` unchanged; one `FEED` per module in `datagen/feeds/`.
- `datagen/generate.py` -- `generate()` builds manifest file entries; add `"era": f.era` only when `f.era` is set (keeps Payer B entries unchanged). `Context.years` (BASE_YEAR 2024), `Context.population(n)` shared households.
- `datagen/npi.py` -- reuse `generate_npi(rng)` / `is_valid_npi()` (Luhn over `80840`+9 digits); do not edit.
- `datagen/population.py` -- `Household`, `Person(person_id, first_name, last_name, sex, dob)`, `Address`; read-only.
- `datagen/feeds/payer_b_members.py` -- pattern to mirror (rng seeding, FeedOutput, person_truth rows).
- `datagen/tests/test_datagen.py` -- `test_manifest_shape_and_sha` asserts the exact file list; extend it with the six new paths. `SMALL = {"records_per_file": 300, "years": 2}`.
- `config/standards/guardrails.yaml` -- `.837` already in `data_extensions`; token `SYNTHETIC-DATA-NO-REAL-PHI`.
- `tools/guardrails.py` marker-check reads first 4096 bytes; read-only.

## Tasks & Acceptance

**Execution:**
- [ ] `datagen/x12.py` -- `Interchange` writer (ISA/GS/ST..SE/GE/IEA with counts and zero-padded control numbers; sender/receiver IDs padded to 15) and `parse(bytes) -> list[list[str]]` using the ISA-declared delimiters -- shared writer and round-trip parser for entries 3 and tests.
- [ ] `datagen/claims837.py` -- shared claim builder: Payer A member id from `person_id` (`PA` + digits, helper `payer_a_member_id(person)` reused by entry 3), eras (`ERAS`, boundary 2024-07-01; A2 changes submitter/sender ID and claim-id prefix), versions (~85% original only, ~10% then replaced (7), ~5% then voided (8); each version its own CLM01, REF*F8 to the original), billing/rendering NPIs via `generate_npi`, embedded ICD-10 and HCPCS Level II lists, code-shaped CPT/CDT; `build(ctx, kind)` returning `FeedOutput` with one `DataFile(..., era=...)` per era named `payer_a_837<kind>_<era>.837`, `records` = claim transactions in the file, `records_per_file` transactions per file; ground truth: `encounter_claim` row per transaction (`encounter_id`, `claim_source` = feed, `claim_id` = CLM01) and `person_truth` rows `source="payer_a"`, `source_record_id` = member id, deduped and sorted.
- [ ] `datagen/feeds/payer_a_837p.py`, `payer_a_837i.py`, `payer_a_837d.py` -- `FEED = Feed("payer_a", "837p"|"837i"|"837d", ...)`; 837P SV1 `HC:<CPT or HCPCS>` + 2310B rendering NM1*82; 837I CLM05 type of bill, CL1, DTP*434/435/096, HI ABK + `HI*DR:<3-digit DRG>`, SV2 `<4-digit revenue code>*HC:<code>`, attending NM1*71; 837D SV3 `AD:<CDT>`, TOO, rendering NM1*82.
- [ ] `datagen/registry.py`, `datagen/generate.py` -- `era` on `DataFile` and manifest.
- [ ] `datagen/tests/test_x12.py` -- parse every generated 837 back to segments; ISA/IEA and GS/GE and SE counts/control numbers; every NM1 `XX` NPI passes `is_valid_npi`; frequency codes 1, 7, 8 present; 7/8 carry REF*F8 to an existing original; both eras present with CI profile (`{"records_per_file": 300, "years": 1}`); every 837I claim has type of bill, DTP*435, DTP*096, SV2 revenue code and DRG; marker in first 4096 bytes; two runs identical SHA-256; manifest era per 837 file; no descriptor text (CPT/CDT match shape regex). Update `test_datagen.py` file-list assertion.

**Acceptance Criteria:**
- Given the repo, when `uv run pytest datagen` runs, then all tests (including the round-trip parse tests) pass.
- Given `make generate PROFILE=demo VOLUME=ci` run twice, when sha256sum of `datagen/out/**` is compared, then they are identical, and `make marker-check PATH=datagen/out` passes.
- Given generated CI output, when `datagen/out/manifest.json` is read, then six 837 entries exist, each with `era` in {A1, A2}, both eras present for each of 837P/I/D.
- Given the repo, when `make validate` runs, then it passes.

## Implementation Notes

- `generate._jsonl` drops exact duplicate rows so a Payer A member seen by several 837 feeds appears once in person_truth.
- `test_datagen.py` upload and Payer B tests updated to expect eight files and filter ground truth by source.
- Simplifications (not certified): one billing HL per claim, 837D has no HI, HL numbering restarts per ST; discharge date is the DTP*434 end, DTP*096 carries discharge hour.
- Follow-ups scheduled past the end of an era's file are dropped, so 7/8 rates are slightly under target near era ends.

## Plan Change Log

## Review Triage Log

### 2026-10-08 — Review pass
- verdicts: 8 findings — high 0, medium 1, low 5, false 2, maybe-false 0
- findings:
  - `[low]` `[patch]` no test for multi-ST files — added test_multi_st_envelopes (1200 claims; GE01>1, ST/SE control numbers and counts, <=500 CLM per ST)
  - `[medium]` `[patch]` 837I DTP*434 end can cross era boundary and file date — end clamped to era last day; file date covers it; test_837i_dates_within_era added
  - `[false]` `[reject]` discharge is time only — discharge date is carried as the DTP*434 RD8 end date, the 5010 institutional convention
  - `[low]` `[defer]` shared _jsonl dedup hides possible duplicate bugs — deferred; stricter per-source dedup adds structure
  - `[low]` `[reject]` pending replacements/voids dropped at file end — output stays consistent; versions 1/7/8 all present; noted in Implementation Notes
  - `[low]` `[reject]` era split assumes years start 2024 — BASE_YEAR is a fixed constant; guard adds complexity for an unreachable case
  - `[low]` `[patch]` 837I CLM06 set / 837D no HI — CLM06 blanked for 837I; 837D HI absence rejected as within "not certified"
  - `[false]` `[reject]` ACs not run — orchestrator ran make validate, marker-check and twice-run sha comparison, all passed

## Design Notes

Segment shape (837P, abbreviated):
```
ISA*00*          *00*          *ZZ*PAYERACH1      *ZZ*PAYERA         *240701*1200*^*00501*000000001*0*T*:~
GS*HC*PAYERACH1*PAYERA*20240701*1200*1*X*005010X222A1~
ST*837*0001*005010X222A1~
BHT*0019*00*SYNTHETIC-DATA-NO-REAL-PHI*20240701*1200*CH~
... HL*1**20*1~ NM1*85*2*...*XX*<npi>~ HL*2*1*22*0~ SBR*P*18*******CI~ NM1*IL*1*<last>*<first>****MI*<member>~
CLM*<id>*<amt>***11:B:7*Y*A*Y*Y~ REF*F8*<original id>~ HI*ABK:E119~ NM1*82*1*...*XX*<npi>~ LX*1~ SV1*HC:99213*125***UN*1***1~ DTP*472*D8*20240703~
SE*<n>*0001~ GE*<st count>*1~ IEA*1*000000001~
```
Era/version facts are recoverable from the file alone (dates and CLM05-3), so later Silver work needs no side channel.

## Verification

**Commands:**
- `uv run pytest datagen` -- expected: pass
- `make generate PROFILE=demo VOLUME=ci` twice + `find datagen/out -type f | sort | xargs sha256sum` diff -- expected: identical
- `make marker-check PATH=datagen/out` -- expected: 0 findings
- `make validate` -- expected: pass

## Auto Run Result

Status: built. Added stdlib X12 005010 writer/parser (`datagen/x12.py`), shared 837 claim builder (`datagen/claims837.py`) and feeds 837P/I/D for Payer A with eras A1/A2 (boundary 2024-07-01), claim frequency 1/7/8 with REF*F8, Luhn NPIs, ICD-10/HCPCS and code-shaped CPT/CDT; manifest carries `era` per 837 file.

Files: `datagen/x12.py`, `datagen/claims837.py`, `datagen/feeds/payer_a_837{p,i,d}.py` (new feeds), `datagen/registry.py` (DataFile.era), `datagen/generate.py` (manifest era, ground-truth dedup), `datagen/tests/test_x12.py` (new), `datagen/tests/test_datagen.py` (file list, source filters).

Review: 3 patches (medium 1, low 2), 1 deferred (low), 4 rejected (2 false, 2 low; reasons in triage log). Follow-up review recommended: false (patched: medium 1, low 2).

Verification: `uv run pytest datagen` 20 passed; two `make generate PROFILE=demo VOLUME=ci` runs identical sha256sum; `make marker-check PATH=datagen/out` 0 findings; `make validate` passed. Not run: `make generate-upload` (not in this ticket's verify; uploads 6 more files next run).

Residual risks: output not certified against the X12 implementation guides; ground-truth dedup in shared writer (deferred).
