---
title: 'X12 834 enrollment and 835 remittance'
type: 'feature'
ticket: '3'
created: '2026-10-08'
status: 'built'
baseline_revision: '9209c596cb8545585bc863cbec910a9b69a669e4'
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
      835 voids reverse the original claim's adjudication even when a frequency-7 replacement superseded it.
    evidence: |-
      payer_a_835._adjudicate negates done[original_id]; claims837 points REF*F8 at the original, so the reversal amount can differ from the latest replacement. Consistent with the plan wording; a later Silver/claims story may want void-of-latest semantics.
    location: >-
      datagen/feeds/payer_a_835.py _adjudicate
    severity: low
---

<intent-contract>

## Intent

**Problem:** Payer A has claims (837) but no enrollment (834 X220A1) or remittance (835 X221A1), so coverage spans and adjudicated amounts are missing from the synthetic sources and ground truth.

**Approach:** Extend entry 2's X12 writer with a transaction-set id and functional id, add a Payer A 834 feed (one full file plus monthly change files; INS03 021/024/001; plan switches with coverage gaps) that writes every true span to `ground_truth/coverage_spans.jsonl`, and an 835 feed that adjudicates every claim produced by the 837 builder (allowed, paid, CAS PR, claim status). Not certified against the guides.

## Boundaries & Constraints

**Always:** Same delimiters/envelope rules as entry 2 (ISA 106 chars, counts and control numbers match, at most 500 members/claims per ST, `~\n`). Marker token within the first 4096 bytes: 834 carries it in `BGN02`, 835 in `REF*EV*<token>` right after TRN. No wall clock; dates derive from data. RNG per feed `f"{seed}:payer_a:{feed}"`. Payer A member ids come from `claims837.payer_a_member_id`, over the same `ctx.population(records_per_file)` the 837 feeds use. 834 spans: `021` opens a span (HD04 plan id, DTP*348 start), `024` closes it (DTP*349 end), `001` is a non-coverage maintenance (address change, N3/N4 differ) and never alters a span; a span with no 024 runs to Dec 31 of the last year. Coverage rows: `{"source": "payer_a", "source_record_id": <member id>, "plan_id": ..., "coverage_start": "YYYY-MM-DD", "coverage_end": "YYYY-MM-DD"}` (Payer B rows unchanged). The 835 reads claims from the 837 builder's in-memory claim list (cached on `Context`), never by re-randomising, so the 837 output stays byte-identical to before. Every CLP: CLP01 = a generated CLM01, CLP02 status, CLP03 charge, CLP04 paid, CLP05 patient responsibility, `CAS*PR` with that amount, `AMT*AU` allowed amount; paid = allowed - PR; frequency 8 (void) claims are status `22` reversals with negated amounts of their original.

**Never:** No third-party X12 libs. No noise/drift/samples (entries 6-10). No change to upload paths, `mpi_eval.ground_truth` (person_truth) schema, or existing 837 bytes. No service-line SVC loops in 835 (claim-level only).

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| CI generate | `make generate PROFILE=demo VOLUME=ci` | 1 full + >=1 change `.834`, 6 `.835` (P/I/D x A1/A2, `era` in manifest), 6 unchanged `.837` | No error expected |
| Plan switch | member switches plan | 024 ends plan X on d, later 021 starts plan Y after d+1 (gap >= 1 day); two spans in truth | No error expected |
| Void claim | 837 freq 8 | 835 CLP02=22, negated amounts, CAS PR present | No error expected |
| Truth check | parse all 834 files | derived spans == coverage_spans.jsonl payer_a rows | test fails on mismatch |

</intent-contract>

## Code Map

- `datagen/x12.py` -- `Interchange.render` hard-codes `ST*837`; add field `set_id: str = "837"` (ST01) keeping defaults so 837 bytes are unchanged. `functional_id` already a field (834 = `BE`, 835 = `HP`). `parse()` reuse as-is. `MAX_PER_ST` = 500.
- `datagen/claims837.py` -- `build(ctx, kind)` builds claims per era (`ERAS`, `era_range`, `VERSIONS`, `RECEIVER`, `SOURCE`, `payer_a_member_id`, `_d8`). Refactor so the per-claim facts (era, claim id, freq, original id, charge `amt`, member id, person, billing tuple `(npi, n, tin)`, svc/latest date, kind) are collected into a list and the result `(FeedOutput, claims)` is cached in `ctx.cache[("837", kind)]`; expose `claims(ctx, kind)`. Do not change RNG call order (837 bytes must match baseline sha).
- `datagen/generate.py` -- `Context`: add `cache: dict = field(default_factory=dict, repr=False)`. `_jsonl` sorts/dedups rows (fine for coverage). Feeds run in module-name order (834, 835 before 837*), so the cache must work regardless of order.
- `datagen/registry.py` -- `DataFile(era=)`, `FeedOutput.coverage_spans`; read-only.
- `datagen/feeds/payer_a_837p.py` -- feed module pattern.
- `datagen/feeds/payer_b_members.py` -- coverage_spans row shape.
- `config/standards/guardrails.yaml` -- `data_extensions` lacks `.834`; add it (`.835` present) so marker-check covers 834 files.
- `datagen/tests/test_datagen.py` -- `test_manifest_shape_and_sha` asserts the exact file list (`SMALL` = 300 records, 2 years); update for new files; other tests filter by source.
- `datagen/tests/test_x12.py` -- `_files` asserts exactly 6 `*.837`; `CI = {"records_per_file": 300, "years": 1}`; pattern for new tests.

## Tasks & Acceptance

**Execution:**
- [x] `datagen/x12.py` -- add `set_id` to `Interchange` -- 834/835 envelopes.
- [x] `datagen/generate.py` -- `Context.cache` -- share 837 claims with 835.
- [x] `datagen/claims837.py` -- collect claim facts and cache; `claims(ctx, kind)` -- 835 input without re-randomising.
- [x] `datagen/feeds/payer_a_834.py` -- `FEED = Feed("payer_a", "834", ...)`: per member a deterministic timeline (most enrolled from window start or a mid-year month; ~20% switch plan with a 1-3 month gap; ~10% terminate; ~15% address change `001`); plans e.g. `PAHMO01`, `PAPPO02`, `PAEPO03`; full file `payer_a_834_full_<YYYYMMDD of window start>.834` (BGN08 `RX`, 021 for members active on day 1) and monthly `payer_a_834_change_<YYYYMM>.834` (BGN08 `2`) for later events, empty months skipped; `records` = INS count; coverage_spans truth; person_truth rows `source="payer_a"` as 837 does.
- [x] `datagen/feeds/payer_a_835.py` -- `FEED = Feed("payer_a", "835", ...)`: per kind and era one file `payer_a_835_<kind>_<era>.835` (`era` set), one ST per billing NPI (payee `N1*PE*...*XX*<npi>`, split at 500 CLPs), BPR total = sum CLP04 for the ST (`C` credit, `D` if negative with abs amount), TRN check number, DTM*405 = latest service date in file + 14 days; per claim LX, CLP, CAS*CO*45 (charge - allowed) when > 0, CAS*PR*1|2 (PR), NM1*QC member, AMT*AU allowed. `records` = CLP count.
- [x] `config/standards/guardrails.yaml` -- add `.834` to `data_extensions`.
- [x] `datagen/tests/test_x12_834_835.py` -- parse every 834/835: envelope counts/control numbers, ST01 834/835 and GS versions X220A1/X221A1; INS03 021, 024, 001 all occur; >=1 full and >=1 change file; >=1 member with two spans separated by a gap; spans re-derived from 834 files equal payer_a coverage_spans.jsonl rows; every CLP01 is a CLM01 in the 837 files, has AMT*AU, CAS*PR, and paid = allowed - PR (2 dp); void reversal check; marker in first 4096 bytes; two runs identical SHA-256 over all files; 837 sha unchanged with and without 834/835 feeds (run with feeds=[837 only] vs all). Update `test_datagen.py` file list and `test_x12.py` if needed.

**Acceptance Criteria:**
- Given the repo, when `uv run pytest datagen` runs, then all tests pass.
- Given `make generate PROFILE=demo VOLUME=ci` run twice, when sha256sum over `datagen/out/**` is compared, then identical, and `make marker-check PATH=datagen/out` reports 0 findings.
- Given the repo, when `make validate` runs, then it passes.

## Implementation Notes

## Plan Change Log

## Review Triage Log

### 2026-10-08 — Review pass
- verdicts: 8 findings — high 0, medium 0, low 7, false 1, maybe-false 0
- findings:
  - `[false]` `[reject]` 835 `done[original_id]` KeyError across eras — claims837 only queues follow-ups inside the same era, after their original, so the lookup always hits
  - `[low]` `[reject]` DTM*405 uses 837I discharge date, not service date — paying 14 days after discharge is the more realistic reading; no consumer depends on it
  - `[low]` `[defer]` void reverses original rather than the frequency-7 replacement — matches plan wording; deferred for void-of-latest semantics
  - `[low]` `[patch]` `_timeline` late-start switch rolls fell into terminate — terminate branch now requires 0.20 <= roll < 0.30
  - `[low]` `[patch]` test hard-codes 20241231 open-span end — derived from BASE_YEAR and CI years
  - `[low]` `[reject]` no golden pin of 837 bytes against the pre-refactor baseline — verified byte-identical manually (implementer and reviewer); a golden hash adds churn for every intended 837 change
  - `[low]` `[patch]` duplicate CLPs undetected — test asserts CLP count equals CLM count
  - `[low]` `[reject]` upload test relaxed to >= 16 — exact file list is pinned by test_manifest_shape_and_sha; upload test asserts cp count == manifest count

## Design Notes

834 member loop (abbreviated):
```
INS*Y*18*024*07*A***FT~ REF*0F*PA00012~ NM1*IL*1*<last>*<first>****ZZ*PA00012~ N3*..~ N4*..~ DMG*D8*<dob>*F~
HD*024**HLT*PAHMO01*EMP~ DTP*349*D8*20240531~
```
835 claim: `CLP*A1P000000012*1*500.00*320.00*80.00*12*PA835000012*11*1~ CAS*CO*45*100.00~ CAS*PR*2*80.00~ NM1*QC*1*..****MI*PA00012~ AMT*AU*400.00~`

## Verification

**Commands:**
- `uv run pytest datagen` -- expected: pass
- `make generate PROFILE=demo VOLUME=ci` twice + `find datagen/out -type f | sort | xargs sha256sum` diff -- expected: identical
- `make marker-check PATH=datagen/out` -- expected: 0 findings
- `make validate` -- expected: pass

## Auto Run Result

Status: built. Added Payer A 834 (X220A1) enrollment feed (one full file BGN08 RX plus monthly change files; INS03 021/024/001; plan switches with 1-3 month gaps; terminations; address-only changes) writing every true span to `ground_truth/coverage_spans.jsonl` (with `plan_id`), and Payer A 835 (X221A1) remittance adjudicating every 837 claim (CLP status/charge/paid/PR, CAS*CO*45, CAS*PR, AMT*AU; voids as status 22 reversals), reading claims from a cache on `Context` so 837 bytes are unchanged.

Files: `datagen/x12.py` (ST01 `set_id`), `datagen/generate.py` (`Context.cache`), `datagen/claims837.py` (claim facts + cache, `claims()`), `datagen/feeds/payer_a_834.py` (new), `datagen/feeds/payer_a_835.py` (new), `config/standards/guardrails.yaml` (`.834` data extension), `datagen/tests/test_x12_834_835.py` (new), `datagen/tests/test_datagen.py` (file list, upload count).

Review: 3 patches (low 3), 1 deferred (low), 4 rejected (1 false, 3 low; reasons in triage log). Follow-up review recommended: false (patched: high 0, medium 0, low 3).

Verification: `uv run pytest datagen` 25 passed; two `make generate PROFILE=demo VOLUME=ci` runs identical sha256sum; `make marker-check PATH=datagen/out` 0 findings; `make validate` passed. 837 files byte-identical to baseline. Not run: `make generate-upload`.

Residual risks: not certified against the X12 guides; 834 enrolls the first 300 persons while 837 claimants come from the whole population, so some 835 claims have no matching coverage span; no denials (all non-void claims status 1).
