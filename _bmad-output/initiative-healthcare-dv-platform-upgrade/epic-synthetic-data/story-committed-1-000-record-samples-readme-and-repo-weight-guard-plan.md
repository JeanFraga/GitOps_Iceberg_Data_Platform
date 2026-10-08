---
title: 'Committed 1,000-record samples, README and repo-weight guard'
type: 'feature'
ticket: '10'
created: '2026-10-08'
status: 'built'
baseline_revision: 'f855d5e32b71bddd8018667dde1583df6a012f45'
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

**Problem:** No generated data is committed, so readers and downstream epics have no in-repo example of each feed; there is no generator README, and nothing stops a large data file from being committed (FR-37).

**Approach:** `make samples` regenerates, deterministically, one sample per feed into `datagen/samples/` from a sample-sized run (records_per_file = 1,000, years = 1, same seed and drift config) together with its manifest and ground truth; `datagen/README.md` documents the generator; a `repo-weight` check in `tools/guardrails.py` (wired into `make validate`) fails on any committed data file outside `datagen/samples/` above the sample record count or the byte limit; `datagen/samples/` is allowlisted for phi-scan.

## Boundaries & Constraints

**Always:** sample size (1000) and byte limit live in `config/standards/guardrails.yaml` under `repo_weight` (`sample_records: 1000`, `max_bytes: 1048576`), read by both the samples command and the guard; samples are byte-identical across reruns; every sample data file carries the synthetic marker; README states the data is synthetic and contains no real PHI.
**Never:** commit `names.txt` into samples (generated names list stays out of git); change `config/schemas/profile.schema.json` or `volume_profiles`; change generator output formats; touch `infra/`.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Rerun samples | `make samples` twice | second run leaves `git status --porcelain` empty | none |
| Oversized file | data file > `max_bytes` outside `datagen/samples/` | `repo-weight` exit 1, finding names file and `bytes` | non-zero exit |
| Too many records | data file with > 1000 records, small bytes, outside samples | exit 1, finding names file and `records` | non-zero exit |
| Inside samples | large data file under `datagen/samples/` | not reported | none |
| Clean repo | committed tree | exit 0 | none |

</intent-contract>

## Code Map

- `datagen/__main__.py` -- add `samples` subcommand: build `Context` like `generate` (train seed, train scenario set, schema/data drift from config) with volume name `sample` and `{"records_per_file": repo_weight.sample_records, "years": 1}`; call `generate(ctx, tmp_out)` into a `tempfile.mkdtemp()` dir, then replace `datagen/samples/` with `landing/<source>/<feed>/*`, `ground_truth/*.jsonl` and `manifest.json` (drop `names.txt`); print one line per feed with record total.
- `datagen/generate.py` -- `generate(ctx, out)` already deterministic and wipes `out`; reuse, do not change.
- `tools/guardrails.py` -- add `repo_weight(path)` and `repo-weight` choice in `main`; default scope = git-tracked files (`_repo_files`, but must NOT honour `allowlist` blindly: skip only `datagen/samples/` plus existing allowlist); data file = `_is_data_file`; records = non-empty lines not starting `#`, minus 1 header line for `.csv`; for X12 extensions (`.x12 .edi .834 .835 .837`) records = count of segments whose id is `CLM`, `CLP` or `INS` (use `datagen`-independent split on `~`).
- `config/standards/guardrails.yaml` -- add `repo_weight` block; add `datagen/samples/` to `allowlist` with a comment that names scanning targets logs/summaries only. Note: marker-check reuses the allowlist, so marker-check on samples must still run — give marker-check its own scope (allowlist minus `datagen/samples/`) or run explicitly; samples must pass `make marker-check`.
- `.gitignore` -- `*.json` is ignored; add `!datagen/samples/manifest.json`.
- `Makefile` -- `samples: resolve` target (`$(UV) run python -m datagen samples`), `repo-weight` target (`$(GUARD) repo-weight $(SCAN_PATH)`), add `repo-weight` to `validate` and `.PHONY`.
- `datagen/README.md` (new) -- modules (registry/feeds, population, noise, drift, data_drift, x12, fhir, estimate, upload), `volume_profile` (`ci`, `full`, `.env` fill rule), local run, full-size run (estimate, budget guard, FORCE), `make samples`, synthetic data / no real PHI statement.
- `tests/test_guardrails.py` -- repo-weight tests per matrix row via `tmp_path` fixtures (path argument).
- `datagen/tests/test_datagen.py` -- one test that `samples` output to a tmp dir is identical across two runs and has one dir per registered feed (monkeypatch the target dir).

## Tasks & Acceptance

**Execution:**
- [x] `config/standards/guardrails.yaml` -- repo_weight block, samples allowlist -- single source for limits.
- [x] `tools/guardrails.py` -- repo-weight check; marker-check still covers samples -- FR-37 guard.
- [x] `datagen/__main__.py` -- samples subcommand -- FR-37 samples.
- [x] `.gitignore`, `Makefile` -- manifest negation, samples/repo-weight targets, validate wiring.
- [x] `datagen/samples/` -- generated by `make samples` and committed.
- [x] `datagen/README.md` -- generator docs.
- [x] `tests/test_guardrails.py`, `datagen/tests/test_datagen.py` -- matrix tests.

**Acceptance Criteria:**
- Given the repo, when `make samples` runs twice, then `git status --porcelain` is empty after the second run and `ls datagen/samples` shows one directory per feed source with every registered feed present, each feed generated at 1,000 records per file.
- Given the samples manifest, then it lists at least one schema-drift and one data-drift entry whose files are in `datagen/samples/`.
- Given the repo, when `make marker-check`, `make phi-scan` and `make repo-weight` run, then all exit 0; given a 2 MB `.csv` placed outside `datagen/samples/`, `make repo-weight PATH=<dir>` exits 1.

## Implementation Notes

- Samples drop the `landing/` prefix (one dir per source); manifest paths rewritten to match. ~7.5 MB committed (45 files). Shared `_context()` helper in `datagen/__main__.py`.

## Plan Change Log

## Review Triage Log

### 2026-10-08 — Review pass
- verdicts: 5 findings — high 0, medium 1, low 4, false 0, maybe-false 0
- findings:
  - `low` `reject` samples exclusion is a substring match on the resolved path — only affects explicit-PATH runs with a nested `datagen/samples/` dir or symlinks; default repo scope already excludes by prefix; fix needs test restructuring.
  - `medium` `patch` repo-weight skipped the whole phi-scan allowlist (tests/fixtures, _bmad-output...) — repo-weight now skips only `datagen/samples/`; repo still passes.
  - `low` `patch` samples test did not check sample size — added assertions on `volume_profile == "sample"` and max file records == `repo_weight.sample_records`.
  - `low` `patch` README module table omitted config/ndc/npi — rows added.
  - `low` `patch` README did not explain per-feed record totals — sentence added on per-era/per-slice/derived counts.

## Design Notes

"1,000-record sample per feed" is read as the feed's output from a run with `records_per_file = 1000` (the generator's sizing unit): 837/835 files hold exactly 1,000 claims, members and pharmacy split 1,000 records across base and drift slices, FHIR reference feeds (organization, practitioner) and providers are derived and smaller. Assumption (autonomous). Measured size ~6 MB without names.txt. Guard byte limit 1 MiB picked for files outside samples (epic Unknown).

## Verification

**Commands:**
- `uv run pytest -q` -- expected: all pass
- `make lint` -- expected: clean
- `make samples && make samples && git status --porcelain` -- expected: empty after committing first run (before commit: only datagen/samples untracked)
- `make marker-check && make phi-scan && make repo-weight` -- expected: exit 0
- `make validate` -- expected: pass

## Auto Run Result

- Summary: `make samples` writes one deterministic sample per feed (records_per_file 1,000, 1 year, drift on) plus manifest and ground truth to `datagen/samples/`; `repo-weight` guard (1,000 records / 1 MiB outside samples) wired into `make validate`; phi-scan allowlists samples; `datagen/README.md` added.
- Files: `datagen/__main__.py` (samples subcommand), `tools/guardrails.py` (repo-weight), `config/standards/guardrails.yaml` (repo_weight, allowlist), `.gitignore` (manifest negation), `Makefile` (samples, repo-weight, validate), `datagen/README.md`, `datagen/samples/` (committed), tests in `tests/test_guardrails.py` and `datagen/tests/test_datagen.py`.
- Review: 4 patches (1 medium, 3 low), 0 deferred, 1 rejected (substring path match, explicit-path only).
- Follow-up review recommended: false (patched: 1 medium, 3 low).
- Verification: pytest 180 passed; make validate passed (lint, tests, phi-scan, marker-check, repo-weight 0 findings); reviewer reran `make samples` twice with clean git status; 2 MB csv outside samples fails repo-weight.
- Residual risks: samples weigh ~7.5 MB; per-feed record totals are not literally 1,000 (assumption in Design Notes).
