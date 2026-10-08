---
title: 'Every sample format into Bronze: NDJSON and X12'
type: 'feature'
ticket: '5'
created: '2026-10-08'
status: 'in-progress'
baseline_revision: '128b3e3e64dcfa58da6ba546ef2f56e955ae3b00'
route: 'full'
route_source: 'auto'
risk: 'medium'
review: ''
review_source: ''
lenses_ran: []
review_loop_iteration: 0
followup_review_recommended: false
context:
  - '{project-root}/_bmad-output/initiative-healthcare-dv-platform-upgrade/epic-landing-bronze/epic-landing-bronze.md'
warnings: []
deferred: []
---

<intent-contract>

## Intent

**Problem:** The loader only handles CSV. A single file that is not CSV is refused with exit 5, and batch mode skips it. That leaves the FHIR NDJSON (`emr_facility_1/*/*.ndjson`) and X12 834/835/837 (`payer_a/{834,835,837d,837i,837p}/*.83?`) samples out of Bronze.

**Approach:** Choose the format from the extension (`.csv`, `.ndjson`/`.jsonl` -> jsonl, `.834`/`.835`/`.837` -> x12). Split with `records.split(data, fmt)` and fingerprint with `config/fingerprint.py` `LAYOUTS[fmt]`. Route through the existing `eras.resolve`. Build rows per format, then send them through the unchanged 3.2 WAP and reconcile gate. Remove the CSV-only refusal.

## Boundaries & Constraints

**Always:**
- Every column is STRING (AD-4).
- NDJSON rows have the columns `record` (one JSON string per line, verbatim) plus the lineage columns.
- X12 rows have the columns `segment_id` (the text before the first element separator) and `segment` (the raw segment text without its terminator) plus the lineage columns.
- The lineage columns are the same as 3.1: `_raw_line, _raw_encoding, _line_ordinal, _ingested_at, _source_file, _record_source, _landed_sha256, _run_id`.
- `_line_ordinal` is the physical line number for NDJSON and the 1-based segment ordinal on the ISA16 terminator for X12 (epic Notes).
- A record that is not UTF-8 gets `_raw_encoding='base64'`, `_raw_line` holding the base64, and NULL data columns.
- The reconcile gate counts the same records the loader writes, because both use `records.split`.
- Keep `_landed_sha256`. Do not use BigQuery reserved prefixes (`_FILE_`, `_PARTITION`, `_TABLE_`, ...).
- Mint one run_id per file in batch.
- Quote identifiers in Spark SQL with backticks, because feed names start with a digit (`834__era_2024`).
- Keep the WAP order, the landed-once rule, the duplicate check and the unmarked check.

**Never:**
- Do not parse X12 loops or flatten FHIR. That is E4 and `ingestion/edi/` (entry 6).
- Do not edit `config/fingerprint.py`, `lifecycle.yaml` or the `ops.*` DDL (E1). The payer_a 834 fingerprint instability stays deferred; both `era_2024` and `era_2024_v2` stay seeded.
- Do not touch the 9 quarantined demo files or the demo `unmarked.csv` row (owner decisions).
- Do not apply Terraform.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| NDJSON happy | `emr_facility_1_patient_F1.ndjson` | Routes to `patient__f1`. One row per line, with `record` holding the line verbatim and `_line_ordinal` the physical line. Reconciled. | none |
| NDJSON blank line | fixture with an empty or CR-only line in the middle | The blank line is not a record (the records.yaml `jsonl.skip_blank: true` rule, applied in `records.split`). Later lines keep their physical ordinals. Loader count and gate count are equal. | none |
| X12 happy, no line breaks | single-line fixture `ISA...*:~GS...~ST...~` | ISA16 (byte 105) is detected. One row per segment, ordinals 1..n, `segment` without `~`. Routes by `x12_layout`. Reconciled. | none |
| X12 with newline after terminator | committed samples (`~\n`) | Same rows as without line breaks; the CR/LF after the terminator is not part of `segment`. Gate SHA-256 is over the stripped segment bytes. | none |
| Non-UTF-8 record | NDJSON line and X12 segment containing byte 0xFF | `_raw_encoding='base64'`, `_raw_line` = base64, data columns NULL, gate passes on the decoded bytes | none |
| Reconcile per format | tamper hook drops one branch row (jsonl and x12) | `quarantined` plus `RECONCILE_FAIL`, main unchanged | exit 4 |
| Bad X12 head | `.835` whose ISA is shorter than 106 bytes | no Bronze write | ValueError; nonzero exit; logs the error type only |
| Unknown extension | `.txt` | single file: exit 5 (`UnsupportedFormat`); batch: skipped and logged | as 3.4 |

</intent-contract>

## Code Map

- `ingestion/__main__.py` -- `load()` with the CSV-only guard and the hardcoded `"csv"`; `run_batch()` with the `.csv` skip.
- `ingestion/bronze.py` -- `build_rows()`, which is CSV-header only; `ensure_table`/`write_branch`, which need identifier quoting.
- `ingestion/records.py` -- `split`, `_split_x12` (ISA16, CR/LF strip), `_split_lf`, and base64 `raw_line`.
- `ingestion/reconcile.py` -- `gate`/`row_bytes`. Reused unchanged.
- `ingestion/marker.py` -- `drop_marker_line` applies to CSV only. The NDJSON and X12 markers are inside records and are kept.
- `config/standards/records.yaml` -- formats.
- `config/fingerprint.py` -- `jsonl_layout`, `x12_layout`. Read only.
- `config/eras/{payer_a,emr_facility_1}.yaml` -- x12 eras `a1/a2/era_2024/era_2024_v2`, jsonl eras `f1`. Already seeded.

## Tasks & Acceptance

**Execution:**
- [x] `config/standards/records.yaml` -- add `skip_blank: true` under `jsonl` -- so blank lines are handled one way by both the loader and the gate.
- [x] `ingestion/records.py` -- honor `skip_blank`, keeping physical ordinals -- the shared split.
- [x] `ingestion/__main__.py` -- add `format_of(uri)`; use per-format split, marker drop (CSV only), fingerprint and layout; remove the batch `.csv` skip; raise `UnsupportedFormat` only for unknown extensions -- this lifts the 3.3/3.4 deferral.
- [x] `ingestion/bronze.py` -- `build_rows(records, fmt, ...)` gains jsonl (`record`) and x12 (`segment_id`, `segment`) layouts; backtick-quote identifiers -- AD-4 layout.
- [x] `ingestion/tests/` -- one test per matrix row, plus a local-Spark NDJSON and X12 WAP reconcile test -- verify clause.

**Acceptance Criteria:**
- Given a fresh table suffix, when each committed NDJSON and X12 sample is loaded, then each file's latest lifecycle state is `reconciled` and the Bronze rows for its `_run_id` equal `len(records.split(file))` (minus the CSV marker line).
- Given a payer_a 834 sample, when it is loaded, then it routes to `era_2024` or `era_2024_v2` and never to `unmapped_*`.
- Given the existing CSV tests, when the suite runs, then they still pass unchanged.

## Design Notes

X12 segment `ISA*00*...*:~` gives `segment_id='ISA'` and `segment='ISA*00*...*:'`. The `_raw_line` lineage column holds the same bytes, which is what the gate hashes. The NDJSON `record` duplicates `_raw_line` for UTF-8 lines, so the data column is still typed for Silver's `JSON_VALUE`.

## Verification

**Commands:**
- `uv run pytest ingestion` -- expected: all pass, including the NDJSON and X12 reconcile tests and the base64 tests.
- `make validate` -- expected: pass.
- Live check, independent of the demo blockers: `uv run python -m ingestion --profile demo --table-suffix _s35 --file <uri>` for one landed NDJSON file (`patient_F1`) and one X12 file (`835_p_A1`), using their existing `ingest_date=2026-10-08` URIs. Expected: exit 0 for each.
- Then `bq query` on `ops.file_lifecycle` by those sha256 values -- expected: latest state `reconciled` with `detail.table` ending `_s35`.
- Then `COUNT(*)` per `_run_id` on `bronze_emr_facility_1.patient__f1_s35` and `bronze_payer_a.835__a1_s35` -- expected: equals the records.yaml split counts.

**Manual checks:**
- The full `make bronze PROFILE=demo` batch is still expected to exit 3 (the `unmarked.csv` row), and the 9 quarantined CSVs stay `quarantined`. The epic's "every sample reconciled" verify is met only once the owner clears both blockers. This story claims all non-CSV samples reconciled, plus the CSVs that were not quarantined.
