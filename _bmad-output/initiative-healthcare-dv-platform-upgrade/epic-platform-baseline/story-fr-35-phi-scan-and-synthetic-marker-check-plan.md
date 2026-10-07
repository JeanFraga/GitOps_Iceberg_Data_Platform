---
title: 'FR-35 PHI scan and synthetic-marker check'
type: 'feature'
ticket: '9'
created: '2026-10-07'
status: 'built'
baseline_revision: '3cd1afcf336429c674bc79e22707ad4b59dc052c'
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
deferred: []
---

<intent-contract>

## Intent

**Problem:** Nothing enforces FR-35 (no PHI-shaped values in logs/summaries) or AD-14's synthetic-only rule (every data file carries the synthetic marker).

**Approach:** `tools/guardrails.py` with `phi-scan` and `marker-check` subcommands driven by `config/standards/guardrails.yaml` (marker token, window, data extensions; PHI regexes and generated-name list; allowlist). Make targets `phi-scan` / `marker-check` take `PATH=` (default: git-tracked repo files minus the allowlist) and join `make validate`. Fixtures in `tests/fixtures/phi/{dirty,clean}` and `tests/fixtures/marker/{marked,unmarked}`.

## Boundaries & Constraints

**Always:** Findings never print the matched value. Exit 1 on findings, 2 on a bad path.

**Never:** No loader-side refusal (E3 loader imports the same spec). No CI workflow (E12).

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| DIRTY | fixture log with SSN | exit 1, file:line: ssn | value not echoed |
| CLEAN | fixture log, no PHI | exit 0 | No error expected |
| NAME | summary with a generated full name, `--names` | exit 1 | No error expected |
| UNMARKED | CSV without token | exit 1 | No error expected |
| MARKED | CSV/JSONL with token in first 4 KiB | exit 0 | No error expected |
| LATE_MARKER | token after 4 KiB | exit 1 | No error expected |
| REPO_DEFAULT | no PATH | allowlisted fixtures skipped, exit 0 | No error expected |
| BAD_PATH | missing dir | exit 2 | error on stderr |

</intent-contract>

## Code Map

- `tools/guardrails.py`, `config/standards/guardrails.yaml`, `tests/test_guardrails.py`, `tests/fixtures/**` -- new.
- `Makefile` -- targets + `validate`; `pyproject.toml` testpaths add `tests`.

## Tasks & Acceptance

**Acceptance Criteria:**
- Given `make phi-scan PATH=tests/fixtures/phi/dirty`, then it fails; given the clean fixture or no PATH, it passes.
- Given `make marker-check PATH=tests/fixtures/marker/unmarked`, then it fails; given marked or no PATH, it passes.

## Implementation Notes

- AD-14 names a synthetic marker but no format. Defined in guardrails.yaml: token `SYNTHETIC-DATA-NO-REAL-PHI` within the first 4096 bytes of every data file (`.csv .jsonl .ndjson .x12 .edi .835 .837 .fhir.json`). The generator (E2) and loader (E3) read the same spec.
- `PATH=` as a make variable replaces make's PATH for recipes; the targets run uv under a fixed system PATH (`TOOL_PATH`) and pass the scan path through `SCAN_PATH` (only set when PATH came from the command line).
- SSN regex matches any `ddd-dd-dddd` (synthetic ranges like 9xx included on purpose). Generated full names: `names:` list or `--names`, empty until datagen exists.
- Repo default scans git-tracked files only (CI scans the checkout).
- Results: dirty -> exit 2 from make (script 1); clean, marked, repo default -> 0; unmarked -> fail.

## Plan Change Log

## Review Triage Log

### 2026-10-07 — Review pass
- verdicts: 6 findings — high 1, medium 2, low 2, false 1, maybe-false 0
- findings:
  - `[high]` `[patch]` test file held a literal SSN, so the repo-default scan would fail once tracked — test now reads the seeded value from the fixture; verified with files staged (tracked): make validate exit 0.
  - `[medium]` `[patch]` `--names nargs=*` swallowed the positional path — now `action=extend, nargs=1` (repeatable); test passes names before the path.
  - `[medium]` `[patch]` name regex had no word boundaries (matched inside uv.lock hashes) — wrapped in `\b(?:...)\b`; whole-word test added.
  - `[low]` `[patch]` tracked-but-deleted file made the default scan exit 2 — `_repo_files` skips paths not on disk.
  - `[low]` `[patch]` fixed TOOL_PATH applied even without PATH= — now only when PATH came from the command line.
  - `[false]` `[reject]` AC exit codes — make 2 wraps script 1; dirty/unmarked fail, clean/marked/default pass, re-checked after commit staging.

## Verification

**Commands:**
- `make validate` -- expected: exit 0, 48 tests
- the four make invocations in the acceptance criteria

## Auto Run Result

- Summary: `tools/guardrails.py` phi-scan (SSN regex + generated-name list, value never echoed) and marker-check (token in first 4 KiB of data files), spec in `config/standards/guardrails.yaml`, make targets with `PATH=` and repo default, both in `make validate`.
- Files: tools/guardrails.py, config/standards/guardrails.yaml, tests/test_guardrails.py, tests/fixtures/{phi,marker}/** (new); Makefile; pyproject.toml.
- Review: 5 patches (1 high, 2 medium, 2 low), 0 deferred, 1 rejected (false).
- Follow-up review recommended: true -- a high was patched (repo-default scan over the tracked test tree); a second pass should confirm no other tracked file carries PHI-shaped literals as the tree grows.
- Verification: make validate exit 0 with all files tracked; 49 tests; dirty/unmarked fail, clean/marked/default pass.
- Residual risks: marker format defined here (AD-14 gave none); datagen (E2) must emit it.
