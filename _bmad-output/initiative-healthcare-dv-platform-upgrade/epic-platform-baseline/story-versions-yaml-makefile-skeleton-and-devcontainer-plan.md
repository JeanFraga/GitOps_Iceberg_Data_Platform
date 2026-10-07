---
title: 'versions.yaml, Makefile skeleton and devcontainer'
type: 'chore'
ticket: '5'
created: '2026-10-07'
status: 'built'
baseline_revision: '25141f5c76748ffef5397fb024c3f6e6ba5036b0'
route: 'oneshot'
route_source: 'auto'
risk: 'medium'
review: 'quick'
review_source: 'pinned'
lenses_ran: [quick]
review_loop_iteration: 0
followup_review_recommended: false
context: []
warnings: []
deferred:
  - summary: >-
      devcontainer build of .devcontainer (python 3.12 base, uv 0.12.23, uv sync --frozen) was never run.
    evidence: |-
      No Docker daemon or devcontainer CLI in the build environment. Settle by running
      `devcontainer build --workspace-folder .` (or rebuilding the Codespace) and confirming post-create succeeds.
    location: >-
      .devcontainer/Dockerfile
    severity: medium (unverified)
---

<intent-contract>

## Intent

**Problem:** Non-registry pins (Dataproc runtime, Iceberg, Fusion, Composer, Cosmos) have no home, there is no Python project or lockfile, the Makefile lacks lint/test, and the devcontainer is on Python 3.11 with an unpinned uv.

**Approach:** Add root `versions.yaml` (AD-20; Cosmos and Composer image marked `inert`), have `config/load.py` resolve it under `versions` in `config/resolved.yaml` so Terraform/runners read pins from one place, add a uv Python 3.12 project (`pyproject.toml`, `uv.lock`, `.python-version`; jsonschema, pyyaml, pytest, ruff), Makefile `lint`/`test` targets with `validate: lint test tf-validate tflint`, and align the devcontainer (python:3.12, uv 0.12.23, `uv sync --frozen` in post-create). Terraform pins stay native.

</intent-contract>

## Tasks & Acceptance

**Acceptance Criteria:**
- Given the repo, when `make validate` runs, then lint, test, tf-validate and tflint pass.
- Given `make resolve`, when reading `config/resolved.yaml`, then `versions.dataproc_runtime` is `3.0` and the Iceberg coordinate ends `:1.12.0`, sourced from `versions.yaml`.
- Given `.devcontainer`, when `devcontainer build` runs, then it succeeds.

## Implementation Notes

Oneshot: ~100 lines across small config files.

- Loader reads `<config_dir>/../versions.yaml` (skipped if absent, so tmp-dir tests stay hermetic); two new tests cover it.
- Ruff scope excludes `_bmad`, `_bmad-output`, `.agents`, `.claude` (vendored tooling). Ruff's active rule set flagged TRY004, so `_read` now raises `TypeError` for a non-mapping file.
- A Terraform `local.versions` was tried and removed: tflint fails on unused declarations. Terraform reaches pins via `local.cfg.versions` when a consumer (E3 Dataproc) needs them.
- devcontainer.json keeps Terraform 1.15.8 (entry 11 bumps it). Java stays for local Spark later.
- `devcontainer build` could not run: no Docker daemon or devcontainer CLI in this environment. Deferred.

## Plan Change Log

## Review Triage Log

### 2026-10-07 — Review pass
- verdicts: 5 findings — high 0, medium 0, low 4, false 0, maybe-false 1
- findings:
  - `[maybe-false]` `[defer]` devcontainer build AC unverified — needs a Docker-capable host to run `devcontainer build`; deferred as medium (unverified).
  - `[low]` `[reject]` validate no longer runs resolve, so stale resolved.yaml passes — entry 3 owns the stale-resolved.yaml check per its ticket text.
  - `[low]` `[patch]` versions.yaml silently replaces a profile `versions` key — documented in load.py docstring that versions.yaml is the only source.
  - `[low]` `[patch]` TypeError for non-mapping YAML escapes main() as a traceback — main() now catches TypeError too.
  - `[low]` `[patch]` module docstring/--help omit versions.yaml — docstring updated.

## Verification

**Commands:**
- `make validate` -- expected: exit 0 (ruff clean, 5 pytest passed, terraform valid, tflint clean)
- `make resolve && git diff --exit-code config/resolved.yaml` -- expected: no diff after commit
- `devcontainer build --workspace-folder .` -- expected: success (not runnable here; deferred)

## Auto Run Result

- Summary: versions.yaml holds non-registry pins (Cosmos, Composer image inert), resolved into config/resolved.yaml under `versions`; uv Python 3.12 project with uv.lock; Makefile lint/test/validate skeleton; devcontainer on python:3.12 + uv 0.12.23 + uv sync.
- Files: versions.yaml, pyproject.toml, uv.lock, .python-version (new); config/load.py, config/test_load.py, config/resolved.yaml; Makefile; .devcontainer/Dockerfile, post-create.sh.
- Review: 3 low patches, 1 deferred (devcontainer build unverified), 1 rejected (stale check owned by entry 3).
- Follow-up review recommended: false (patched: low 3).
- Verification: make validate exit 0 (ruff clean, 5 tests, terraform valid, tflint clean); make resolve reproduces committed resolved.yaml.
- Residual risks: devcontainer build untested here.
