---
title: 'Hash and fingerprint specs with golden vectors'
type: 'feature'
ticket: '4'
created: '2026-10-07'
status: 'built'
baseline_revision: '761e9112674db263942a93b05fdb729a451964d8'
route: 'full'
route_source: 'auto'
risk: 'medium'
review: 'quick'
review_source: 'pinned'
lenses_ran: [quick]
review_loop_iteration: 0
followup_review_recommended: true
context: []
warnings: []
deferred:
  - summary: >-
      X12 fingerprint uses distinct segment ids (first-occurrence order) of the first ST..SE set; AD-22 text says "ordered segment-id layout".
    evidence: |-
      A literal reading (every segment incl. repeated loops) makes the fingerprint vary with claim count,
      sending files to unmapped_<fp8> -- the failure AD-22 exists to prevent. Decision recorded in
      config/standards/fingerprint.yaml; AD-22 wording in the architecture doc should be amended to match, or the owner overrules.
    location: >-
      config/fingerprint.py x12_layout
    severity: medium
---

<intent-contract>

## Intent

**Problem:** Spark, dbt, MPI and the onboarding CLI need one shared definition of vault hash keys (AD-7) and schema fingerprints (AD-22), plus the closed file-lifecycle enum (AD-4/AD-10) and the open D-7 drift key; none exist yet.

**Approach:** Add `config/standards/hashing.yaml` and `config/standards/fingerprint.yaml` (spec + golden vectors), Python reference implementations `config/hashing.py` and `config/fingerprint.py`, pytest running every vector, `config/standards/lifecycle.yaml` validated by `make validate-config` against `config/schemas/lifecycle.schema.json`, and a `drift` key in defaults (`data_drift_thresholds: null`, `mode: report_only`) added to the profile schema.

## Boundaries & Constraints

**Always:** Vector `canonical` strings are written from the rules, not produced by the implementation; `md5`/`sha256` are computed from them. Business-key uppercase is ASCII-only. One fingerprint implementation.

**Never:** No business_keys.yaml or per-hub vectors (vault epics own recipes). No Spark/dbt implementations.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| BK_NORMALIZE | NFC, trim, ASCII upper, non-ASCII kept | canonical per vector | No error expected |
| NULL_SENTINEL | empty/whitespace/None | `^^` | No error expected |
| ESCAPE | `|`, `\\` in value | escaped | No error expected |
| ALL_NULL_BK | every component null | rejected | AllNullBusinessKeyError |
| FORMATS | date, tz timestamp, decimal | ISO / UTC micro Z / no trailing zeros | naive ts ValueError, float TypeError |
| FP_CSV | BOM, quoted, NFC header | lowercased trimmed names | No error expected |
| FP_JSONL | blank lines, nested, > N records | sorted top-level key union of first N | non-object TypeError |
| FP_X12 | two ST..SE sets, repeated loops | distinct ids of first set | missing ISA/ST..SE ValueError |
| LIFECYCLE_BAD | unknown state in lifecycle.yaml | validate-config exit 1 | ConfigError |

</intent-contract>

## Code Map

- `config/hashing.py`, `config/fingerprint.py` -- reference implementations.
- `config/standards/{hashing,fingerprint,lifecycle}.yaml` -- specs and vectors.
- `config/schemas/lifecycle.schema.json`, `config/schemas/profile.schema.json` (`drift`) -- contracts.
- `config/load.py` `validate_standards` -- run by `--validate-only`.
- `config/test_golden_vectors.py`, `config/test_load.py`.

## Tasks & Acceptance

**Acceptance Criteria:**
- Given the repo, when `pytest config/` runs, then every hash and fingerprint golden vector passes.
- Given lifecycle.yaml and the D-7 key at its default, when `make validate-config` runs, then it passes; an unknown lifecycle state fails it.

## Implementation Notes

- AD-22 says X12 uses the "ordered segment-id layout of the first transaction set". Taking every segment would make the fingerprint depend on the number of claims/loops, so the spec fixes it as distinct segment ids in first-occurrence order; recorded in fingerprint.yaml.
- JSONL N = 100, mirrored by `JSONL_SAMPLE_RECORDS` and asserted equal in a test.
- First draft of the NFC vector folded `é` to `É`; AD-7 says ASCII uppercase only, so the canonical is `CAFé`. Fixed in the vector, not the code.
- Hash spec quirk kept as written: a literal value `^^` hashes the same as NULL.
- `make check-resolved` caught the stale resolved.yaml after adding `drift`; regenerated.

## Plan Change Log

## Review Triage Log

### 2026-10-07 — Review pass
- verdicts: 7 findings — high 1, medium 2, low 4, false 0, maybe-false 0
- findings:
  - `[high]` `[patch]` lifecycle `quarantined -> silver_loaded` contradicts architecture state diagram — now `quarantined: [reconciled, landed]`.
  - `[medium]` `[patch]` jsonl_layout used splitlines(), breaking on U+2028 inside JSON strings — split on LF, strip trailing CR; test added.
  - `[low]` `[patch]` empty CSV fingerprints as sha256('') — raises ValueError; test added; spec text updated.
  - `[low]` `[patch]` no golden vectors for boolean, float, naive timestamp — vectors added (boolean canonical, three error vectors).
  - `[low]` `[patch]` NaN/Infinity Decimal hashed — rejected with ValueError; spec + error vector added.
  - `[medium]` `[defer]` X12 distinct-id layout departs from AD-22 wording — design reason recorded; architecture wording needs owner confirmation.
  - `[low]` `[patch]` hashing.yaml comment claimed CI runs vectors — reworded (Python pytest now; CI with E12).

## Verification

**Commands:**
- `uv run pytest config/` -- expected: 36 passed
- `make validate` -- expected: exit 0

## Auto Run Result

- Summary: AD-7 hash spec + Python reference (`config/hashing.py`), AD-22 fingerprint spec + single implementation (`config/fingerprint.py`), golden vectors for both run by pytest, lifecycle.yaml validated by validate-config, D-7 `drift` key defaulting to unset/report_only.
- Files: config/hashing.py, config/fingerprint.py, config/test_golden_vectors.py, config/standards/{hashing,fingerprint,lifecycle}.yaml, config/schemas/lifecycle.schema.json (new); config/load.py, config/test_load.py, config/schemas/profile.schema.json, config/defaults.yaml, config/resolved.yaml.
- Review: 6 patches (1 high, 1 medium, 4 low), 1 deferred (X12 layout vs AD-22 wording), 0 rejected.
- Follow-up review recommended: true -- a high (lifecycle edges) was patched; the patched transition graph has no test that compares it edge-by-edge to the architecture diagram.
- Verification: pytest 41 passed; make validate exit 0.
- Residual risks: X12 layout interpretation awaiting owner confirmation.
