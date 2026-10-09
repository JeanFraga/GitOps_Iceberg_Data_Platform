---
title: 'EDI pre-parse to a line-oriented derivative'
type: 'feature'
ticket: '6'
created: '2026-10-08'
status: 'built'
baseline_revision: '29a7fad0b037fb3a3840daac4b02b76706a13d04'
route: 'full'
route_source: 'auto'
risk: 'low'
review: 'quick'
review_source: 'pinned'
lenses_ran: ['quick']
review_loop_iteration: 0
followup_review_recommended: false
context: ['{project-root}/_bmad-output/initiative-healthcare-dv-platform-upgrade/epic-landing-bronze/epic-landing-bronze.md']
warnings: []
deferred: []
---

<intent-contract>

## Intent

**Problem:** Silver (E4) needs X12 as one record per segment with its envelope context, but raw X12 is one terminator-delimited stream with nested ISA/GS/ST envelopes. AD-4 and the epic Notes call for a deterministic pre-parse derivative under `gs://<project>-warehouse/edi_preparse/`, checked byte-identical in CI.

**Approach:** Add `ingestion/edi/` with a pure function from raw bytes to JSONL bytes. It reuses `ingestion/records.split(data, "x12")` (ISA16 split, 1-based ordinals) and the element-separator rule that `bronze.py` already uses (ISA byte 4). Add a CLI with a `--landing` flag that writes to the warehouse bucket, and a `make edi-preparse-check` target wired into `make validate`.

## Boundaries & Constraints

**Always:** One record per X12 segment, with keys `source_file`, `source_sha256`, `isa_control`, `gs_control`, `st_control`, `segment_id`, `segment_ordinal` and `elements` (the list of raw element strings). Serialize with `json.dumps(sort_keys=True, separators=(",", ":"), ensure_ascii=False)`, end every line with `\n`, and use no timestamps, run ids or absolute paths. Read the raw file read-only. The landing path is `edi_preparse/source=<source>/feed=<feed>/sha256=<sha>/<name>.jsonl`.

**Never:** Duplicate the ISA16 split or the separator logic. Never write to, rename or touch the raw file or the landing bucket. Never use Spark or third-party X12 libraries, never write Bronze or `ops.*` rows, and never decide how Silver consumes the derivative (that is E4's choice).

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|---|---|---|---|
| Deterministic bytes | any sample X12 | sorted keys, `,`/`:` separators, LF only, UTF-8 | none |
| Regeneration | same file run twice | byte-identical output | check fails on any diff |
| Segment count | sample with N segments from `records.split` | N JSONL lines, ordinals 1..N | count mismatch fails the test |
| Hand-edited golden | one byte changed in a golden | `make edi-preparse-check` exits 1 and names the file | non-zero exit |
| Nested controls | ISA > GS > multiple ST; IEA/GE/SE trailers | each segment carries the enclosing ISA13/GS06/ST02; ISA/IEA carry only the ISA value (others null), GS/GE add GS | none |
| Raw untouched | raw file | mtime, size and sha256 unchanged after the run | test asserts this |
| Bad input | not starting with a full ISA | — | `ValueError` from `records.split`, exit 1 |

</intent-contract>

## Code Map

- `ingestion/records.py` -- `split(data, "x12")` / `_split_x12`: ISA16 split and segment ordinals (reuse)
- `ingestion/bronze.py` -- the x12 element separator (ISA byte 4); factor it into `records.py` if needed so both callers share it
- `ingestion/__main__.py`, `ingestion/land.py` -- the existing CLI and GCS write patterns that the `--landing` mode follows
- `tools/guardrails.py`, `config/standards/guardrails.yaml` -- marker-check (`.jsonl` is a data extension, with the token within 4096 bytes) and repo-weight (1 MiB and 1000 records per file outside `datagen/samples/`)
- `datagen/samples/payer_a/{835,837d,837i,837p}/` -- 12 X12 samples, 4.3 MB raw, up to about 25.7k segments per file
- `Makefile` -- the `validate` target

## Tasks & Acceptance

**Execution:**
- [ ] `ingestion/edi/__init__.py`, `ingestion/edi/preparse.py` -- `preparse(data: bytes, name: str) -> bytes`, which tracks the control numbers through the nested envelopes -- the core of the story
- [ ] `ingestion/edi/__main__.py` -- `python -m ingestion.edi <file> [--out DIR | --landing --source --feed]` -- local and landing modes
- [ ] `ingestion/edi/check.py` -- regenerates every sample twice, compares the two runs with each other and with the goldens, and has an `--update` flag -- the CI check
- [ ] `ingestion/edi/tests/golden/` -- the committed goldens (see Design Notes on size)
- [ ] `ingestion/edi/tests/test_preparse.py` -- the matrix cases, including a small nested ISA/GS/multi-ST fixture
- [ ] `Makefile` -- add an `edi-preparse-check` target and append it to `validate`

**Acceptance Criteria:**
- Given the committed goldens, when `make validate` runs, then `edi-preparse-check`, `marker-check` and `repo-weight` all pass.
- Given a golden with one changed byte, when `make edi-preparse-check` runs, then it exits non-zero.
- Given a sample's derivative, when its BHT line is read, then the `SYNTHETIC-DATA-NO-REAL-PHI` token appears within the first 4096 bytes, because the elements are kept raw.
- Given `--landing`, when the command runs on one landed file, then exactly one object is written at the `edi_preparse/...` path and the landing object is unchanged.

### 2026-10-09 — Review pass
- verdicts: 8 findings — high 0, medium 1, low 5, false 2, maybe-false 0
- findings:
  - `medium` `patch` Non-UTF-8 segments were silently replaced with U+FFFD. Fixed: raw_b64 plus the encoding flag, elements null; test added.
  - `low` `patch` The landing "exists" branch kept a stale object. Fixed: compares bytes; a conflict exits 1 and never overwrites.
  - `low` `patch` The resolved.yaml load was outside the error path, and stderr was dropped. Fixed: structured error with the gcloud return code.
  - `low` `patch` --out and --landing were both accepted. Fixed: mutually exclusive group.
  - `low` `reject` 834 samples included (25 instead of 12). Broader coverage is harmless; goldens are hash-based.
  - `false` `reject` Determinism is only checked in-process. The code has no hash-seed or ordering source; output is from sorted keys.
  - `low` `patch` Test gaps. Added a readable-golden tamper test; the other gaps are covered by marker-check and the landing tests.
  - `false` `reject` Plan checkboxes unticked. The fix would edit the plan.

## Auto Run Result

- Summary: ingestion/edi pre-parse writes a deterministic JSONL derivative per X12 file with envelope control numbers. make edi-preparse-check (in validate) verifies byte-identical regeneration against committed hash goldens plus one readable golden.
- Files: ingestion/edi/{preparse,__main__,check}.py, ingestion/edi/tests/*, ingestion/records.py (x12_element_separator), ingestion/bronze.py, Makefile.
- Review: 5 patched (1 medium, 4 low), 0 deferred, 3 rejected.
- Follow-up review recommended: false.
- Verification: make validate gave 342 passed, edi-preparse-check reported 26 goldens match, and marker-check and repo-weight passed. A hand-edited golden fails the check. The live landing write was not run (optional).

## Design Notes

Golden size gap: a full-sample derivative adds the file name, a 64-character sha256 and the control numbers to each of up to about 25.7k segments. That is several MB and many more than 1000 lines per file, so it breaks `repo-weight` (1 MiB and 1000 records) for every sample. The default is to commit a golden per sample as `<name>.jsonl.sha256`, which holds the sha256 of the derivative and its line count. That file is not a data extension and its size is trivial, and editing it by hand still fails the check. Alongside it, commit one full `.jsonl` golden for the smallest sample, truncated to its first ST transaction set (under 1000 lines), so reviewers can read the format. That file must keep the marker within 4 KB. If the owner wants full JSONL goldens instead, `guardrails.yaml` needs an allowlist entry for `ingestion/edi/tests/golden/`, which would be a guardrail change.

## Verification

**Commands:**
- `uv run pytest ingestion/edi/tests -q` -- expected: pass
- `make edi-preparse-check && make marker-check && make repo-weight` -- expected: exit 0
- `make validate` -- expected: exit 0, with edi-preparse-check listed

**Manual checks (if no CLI):**
- Optional live check on one file: run `uv run python -m ingestion.edi gs://<project>-landing/<one .837> --landing --source payer_a --feed 837p`, then `gcloud storage ls gs://<project>-warehouse/edi_preparse/** --quiet --format=value(name)`. Expect one object and an unchanged landing object.
