---
title: 'Refactor sweep (epic-synthetic-data)'
type: 'refactor'
ticket: '11'
created: '2026-10-08'
status: 'built'
baseline_revision: 'cd0813f411d89e6450c4998a640224ae3545f4a7'
route: 'oneshot'
route_source: 'auto'
risk: 'low'
review: 'quick'
review_source: 'pinned'
lenses_ran: ['quick']
review_loop_iteration: 0
followup_review_recommended: false
context: []
warnings: []
deferred: []
---

<intent-contract>

## Intent

**Problem:** Sibling plans of epic-synthetic-data deferred nine review findings. Some are small cleanups; others need new scope or change generator output.

**Approach:** Clear the cleanup-sized findings only: Makefile config targets use the PATH-safe `$(UV)` wrapper; `make phi-scan` passes `--names-file datagen/out/names.txt` when that file exists; `generate-upload` help warns it reads `datagen/out/` (CI output); a FHIR test ties each Encounter subject to the NM1*IL member of its claims; a test asserts no feed emits duplicate ground-truth rows before the writer dedup. Generator output must stay byte-identical (baseline `make generate VOLUME=ci` tree digest 6fff9ccb5525744472a1fed51d20bd30da0552043f6bbd0615fce1ac919dfae7). Left deferred (new scope or output change): budget headroom via billing export, atomic ground-truth reload, 835 void-of-latest semantics.

</intent-contract>

## Implementation Notes

Oneshot: about 40 lines across Makefile and two test files; no generator code changes.

## Plan Change Log

## Review Triage Log

## Verification

**Commands:**
- `make validate` -- expected: passes
- `make generate VOLUME=ci` then tree digest of datagen/out -- expected: equals baseline above

## Auto Run Result

Status: blocked. Blocking condition: no subagents (the quick review lens launched detached, not blocking; the workflow forbids awaiting it).
Implemented, verified, unreviewed and uncommitted: Makefile ($(UV) for config targets, phi-scan --names-file when datagen/out/names.txt exists, generate-upload help warning), datagen/tests/test_fhir.py (encounter subject = claim NM1*IL member), datagen/tests/test_datagen.py (no per-feed duplicate truth rows). make validate passes; VOLUME=ci digest unchanged (6fff9ccb...dfae7).

## Orchestrator review

2026-10-08: the review subagent could not run blocking; with the user's standing authorization the orchestrating session reviewed the 3-file diff, re-ran `make validate` and `make phi-scan` (0 findings), and committed.
