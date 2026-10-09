---
title: 'Storage-class reconciler for landing'
type: 'feature'
ticket: '7'
created: '2026-10-09'
status: 'built'
baseline_revision: 'b3659f183aab123915fbe1b35e252096d35189bf'
route: 'oneshot'
route_source: 'auto'
risk: 'low'
review: 'quick'
review_source: 'pinned'
lenses_ran: ['quick']
review_loop_iteration: 0
followup_review_recommended: false
context:
  - '{project-root}/_bmad-output/initiative-healthcare-dv-platform-upgrade/epic-landing-bronze/epic-landing-bronze.md'
warnings: []
deferred: []
---

<intent-contract>

## Intent

**Problem:** The Coldline (7-day) and Archive (60-day) transitions that E1's bucket lifecycle rules apply to landing objects are never recorded, so `ops.file_lifecycle` cannot show where a delivery's raw bytes live (Done when 1).

**Approach:** Add `make reconcile-storage PROFILE=demo` (a new `ingestion/storage_class.py` module, kept separate from the loader and era code). It lists landing objects with their storage class in one `gcloud storage ls --json`-style call, and joins them by URI to the latest `storage_class` per file in `ops.file_lifecycle`. For each object whose class differs, it appends one row: the file's current latest `state` repeated unchanged, `storage_class` set to the observed class, and `detail` `{"storage_class_from": <prev or null>, "storage_class_to": <new>}`. Objects with no lifecycle row are left alone (discovery owns `landed`). A rerun with no changes appends nothing.

</intent-contract>

## Implementation Notes

Oneshot: about 100 lines, one new module plus a Makefile target and tests. Reuse:
- `ingestion/discover.py` for listing and URI parsing
- `ingestion/lifecycle.py` for its parameterized bq pattern, with `--project_id` and `--maximum_bytes_billed` from resolved.yaml

Logs carry no row values. Use non-interactive flags. Insert the rows in chunks so the bq parameter size stays bounded; this addresses 3.4's deferred item only for this path.

Tests (fake listing and fake ops backend):
- One object moving STANDARD → COLDLINE → ARCHIVE across three runs produces exactly two class-move rows, plus the first STANDARD row if none was recorded.
- An identical rerun appends nothing.
- An object with no lifecycle row is skipped.

Live: run `make reconcile-storage PROFILE=demo` twice. The first run records STANDARD once for each landed object with lifecycle rows; the second records nothing. Check with a `bq query` grouped by `file_sha256`, `object_uri` and `storage_class`.

## Verification

**Commands:**
- `uv run pytest ingestion` -- all pass
- `make validate` -- passes
- `make reconcile-storage PROFILE=demo` run twice -- the second run logs 0 rows appended

## Review Triage Log

### 2026-10-09 — Review pass
- verdicts: 1 findings — high 0, medium 1, low 0, false 0, maybe-false 0
- findings:
  - `medium` `patch` The latest row's storage_class is empty whenever the loader writes a later state (lifecycle.record writes ''), so the reconciler would re-record the class after every state change. Fixed: compare against LAST_VALUE(NULLIF(storage_class,'') IGNORE NULLS); test added. The live demo rerun gave 0 rows.

## Auto Run Result

- Summary: `make reconcile-storage` lists landing classes with one gcloud call, joins them to the last recorded class per object, and appends a class-move row (state unchanged, detail from/to) in chunked inserts.
- Files: ingestion/storage_class.py, ingestion/tests/test_storage_class.py, Makefile.
- Review: 1 patched (medium), 0 deferred, 0 rejected.
- Follow-up review recommended: false.
- Verification: pytest ingestion passed. Live: the first run appended 3 rows (19 of the 22 tracked objects already had STANDARD); after the patch, two reruns appended 0. 40 objects have no lifecycle row (the pre-intake full-size run) and are skipped, as specified.
