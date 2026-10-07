---
title: 'Config contract schema, template profile and validate-config'
type: 'feature'
ticket: '3'
created: '2026-10-07'
status: 'built'
baseline_revision: '486b120f6ddea3a98ac97e84974f50d081b8ee21'
route: 'full'
route_source: 'auto'
risk: 'medium'
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

**Problem:** The config loader merges YAML with no contract: unknown keys, wrong flag names or a cost flag switched on in defaults pass silently, there is no onboarding profile, and nothing catches a hand-edited `config/resolved.yaml`.

**Approach:** Extend `config/load.py` with JSON Schema validation (`config/schemas/profile.schema.json`, Draft 2020-12): top-level and `flags` `additionalProperties: false`, the four AD-1 flag keys exact and required; a defaults check that the three cost flags are false and `ml_fallback_enabled` true. Add `config/profiles/_template.yaml`, `make validate-config` (demo and `_template`), and `make check-resolved` (`--check`: exit 1 when resolved.yaml differs from a fresh render); both join `make validate`.

## Boundaries & Constraints

**Always:** Validation runs before any write; an invalid profile never writes resolved.yaml. Schema is the single contract; later entries add keys to it.

**Never:** No change to Terraform or to the resolved.yaml shape.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| VALID | demo or _template profile | `--validate-only` prints ok, exit 0 | No error expected |
| UNKNOWN_FLAG | profile adds `flags.looker_enabled` | exit 1 naming the key | schema error list on stderr |
| UNKNOWN_KEY | profile adds top-level `surprise` | exit 1 | schema error |
| COST_DEFAULT_ON | defaults `composer_enabled: true` | exit 1 naming the flag | ConfigError |
| ML_DEFAULT_OFF | defaults `ml_fallback_enabled: false` | exit 1 | ConfigError |
| STALE | resolved.yaml missing or hand-edited | `--check` exit 1 | message says run make resolve |
| INVALID_WRITE | profile missing project_id | `make resolve` exit 1, no file | schema error |

</intent-contract>

## Code Map

- `config/load.py` -- `validate`, `check_defaults`, `render`, `is_stale`, `ConfigError`; CLI `--validate-only` / `--check` (mutually exclusive).
- `config/schemas/profile.schema.json` -- contract; `.gitignore` un-ignores `config/schemas/*.json` (repo ignores `*.json`).
- `config/test_load.py` -- one test per matrix row plus repo-profile validation.
- `Makefile` -- `validate-config`, `check-resolved`; `validate: lint test validate-config check-resolved tf-validate tflint`.

## Tasks & Acceptance

**Acceptance Criteria:**
- Given demo and _template, when `make validate-config` runs, then it passes; given an unknown flag key in a profile, then it fails.
- Given config/resolved.yaml edited by hand, when `make check-resolved` runs, then it exits nonzero.

## Implementation Notes

Implemented in the main session (route full by size, but the change is cohesive in four files). A Makefile insert initially duplicated targets because `lint: ##` also matched inside `tflint: ##`; fixed and `make help` checked.

CLI checks: unknown `flags.bogus_enabled` in demo -> `make validate-config` exit 2 with "'bogus_enabled' was unexpected"; `sed` edit of resolved.yaml -> `make check-resolved` exit 2; restored -> ok.

## Plan Change Log

## Review Triage Log

### 2026-10-07 — Review pass
- verdicts: 3 findings — high 0, medium 1, low 1, false 1, maybe-false 0
- findings:
  - `[medium]` `[patch]` defaults cost-flag check ran only under --validate-only, so make resolve could write an off-contract config — check_defaults moved into render(); test added that a cost flag on blocks the write.
  - `[low]` `[patch]` `flags:` with null value crashed check_defaults with AttributeError — now `.get("flags") or {}`.
  - `[false]` `[reject]` notes record exit 2 vs matrix exit 1 — 2 is make's wrapper code; unit tests assert the script returns 1.

## Verification

**Commands:**
- `make validate` -- expected: exit 0, 12 tests pass
- `make validate-config` with an unknown flag in demo.yaml -- expected: nonzero
- `make check-resolved` after a hand edit -- expected: nonzero

## Auto Run Result

- Summary: JSON Schema contract for the resolved config (exact flag keys, additionalProperties false), defaults check (cost flags off, ml_fallback on) before any write, _template profile, `make validate-config` and `make check-resolved`, both in `make validate`.
- Files: config/load.py; config/schemas/profile.schema.json (new); config/profiles/_template.yaml (new); config/test_load.py; Makefile; .gitignore (un-ignore schemas).
- Review: 2 patches (1 medium, 1 low), 0 deferred, 1 rejected (false).
- Follow-up review recommended: false (patched: medium 1, low 1).
- Verification: make validate exit 0; 13 tests pass; CLI: unknown flag -> validate-config fails; hand-edit -> check-resolved fails.
- Residual risks: none known.
