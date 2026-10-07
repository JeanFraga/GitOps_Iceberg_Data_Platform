# Review — Data Integrity & PHI Lens

Spine: `architecture-healthcare-dv-platform-upgrade.md` (draft, 2026-10-07). Authority: `.memlog.md` (later supersedes earlier).
Scope: hash/key determinism, idempotency, late arrival, MPI survivorship / must-not-link, audit trail, lineage, PHI exposure paths, key management.

**Verdict:** the spine's structure is sound (single contract, one writer per table, insert-only vault, ops log, PHI dataset split). It is **not yet build-safe for integrity or PHI**: the HMAC tokenization in AD-14 can't be built as written, there is no writer for `restricted_phi`, cross-engine hashing leaves out the details that usually cause mismatches, Bronze and MPI writes are not idempotent, and several PHI paths (raw-line Bronze, ops detail, runtime logs, dbt test failures, MPI scratch, quasi-identifiers in `gold_deid`) are unaddressed.

## Findings

### Critical

**C1. AD-14 HMAC tokenization can't be built as written.** BigQuery has no HMAC function and an authorized view can't read Secret Manager at query time. Putting the key into view SQL exposes it to anyone who can see the view definition.
*Fix (amend AD-14 + AD-2):* add a dedicated token job (Python, runtime-token SA, the only principal with `secretAccessor` on the HMAC secret) that writes `restricted_phi.person_token(golden_person_hk, token, key_version, created_run_id)` using HMAC-SHA256(key_vN, golden_person_hk), insert-only. `gold_deid` views join this table and project only `token`. Add it to AD-2's writer list. Alternative: `DETERMINISTIC_ENCRYPT` with a KMS-wrapped keyset (`KEYS.KEYSET_CHAIN`). That approach is reversible encryption, not a one-way token, so record the choice if it is used.

**C2. No writer and no physical rule for `restricted_phi`. Silver PHI is ungoverned.** AD-14 says PHI columns "live in restricted_phi", but AD-8 has Spark write full canonical Silver (patient name, DOB, address, member ID) to `silver`, and AD-2 assigns no writer for `restricted_phi`.
*Fix:* choose one approach and state it in AD-8/AD-14. (a) Spark writes PHI-tagged columns to `restricted_phi.<entity>_phi` keyed by `(_file_sha256,_line_ordinal)` plus the business key, and `silver.<entity>` carries no PHI-tagged columns. Or (b) Silver keeps PHI and every PHI-tagged column gets a BigQuery policy tag (taxonomy generated from config tags by Terraform) with fine-grained reader granted only to the runtime SA. The same rule applies to vault sats: PHI sats (`SAT_*_DEMOGRAPHICS`) go to `restricted_phi`. Raw Vault keeps only hash keys.

**C3. Unsalted MD5 business keys are re-identifiable.** `member_hk = MD5(PAYER||MEMBER_ID)` and patient/MRN keys come from low-entropy identifiers and can be reversed with a dictionary attack. `restricted_phi` is "joined by hash key", so any consumer holding hash keys can reverse them.
*Fix (AD-14):* `gold_deid` exposes no vault hash key (`*_hk`, `hashdiff`), only HMAC tokens (C1), including claim/visit tokens where a row key is needed. Add a CI check that fails if any `gold_deid` view projects a `*_hk` column.

### High

**H1. AD-7 is underspecified for deterministic results across Python and SQL.** Points of divergence:
- Unicode: Python `str.upper()` maps `ß`→`SS`, BigQuery `UPPER` does not. Python `strip()` removes all Unicode whitespace, BigQuery `TRIM` behaves differently.
- Type-to-string formatting: DATE, TIMESTAMP precision and zone, NUMERIC scale/exponent, FLOAT, BOOL.
- An empty string after trim vs NULL.
- A value containing `||` or `^^`.
- Column order in hashdiff.
- Encoding.
- A business key that is all null.

*Fix (expand `config/standards/hashing.yaml`):*
- UTF-8, NFC-normalize, then trim ASCII space/tab/CR/LF only.
- Uppercase ASCII-only for business keys. Hashdiff payloads are NOT uppercased, because uppercasing hides real corrections to case-sensitive values.
- Empty string after trim → NULL → `^^`.
- Escape `\`, `|`, `^` in values before joining.
- Canonical formats: DATE `YYYY-MM-DD`, TIMESTAMP UTC `YYYY-MM-DDTHH:MM:SS.ffffffZ`, NUMERIC as plain decimal at the declared scale, BOOL `TRUE`/`FALSE`, no FLOAT in keys or hashdiff.
- Hashdiff columns sorted by the order declared in config, not by SELECT order.
- An all-null business key → reject to quarantine (never hash it).
- Golden vectors must cover every rule above. All three engines run them, including Spark if it ever computes keys.

**H2. Bronze append isn't idempotent.** A retry after a partial or failed write appends a second snapshot of the same file. The reconcile gate then sees 2x rows, quarantines the file, and nothing in the spine fixes it ("never updated").
*Fix (AD-4):* use the Iceberg write-audit-publish pattern. Write each delivery to branch `wap_<file_sha256>`, run reconcile against the branch, then fast-forward to `main` and append `bronze_loaded`. Before writing, check `file_lifecycle` and skip if `bronze_loaded` already exists for that sha. A failed branch is dropped, not left in `main`. This also resolves the open question of where reconcile runs relative to the snapshot.

**H3. MPI "insert-only per run_id" duplicates on rerun and is not reproducible.** A rerun of the same input gets a new `run_id` and re-inserts every link and score. Splink EM training and blocking samples are nondeterministic.
*Fix (AD-13):*
- Link rows are keyed by a deterministic link hk and inserted only if absent.
- Score rows go in `SAT_MPI_MATCH_DETAILS` with a hashdiff, so a rerun with identical output is a no-op.
- Fix the random seed. Persist the trained Splink model JSON and the XGBoost model as versioned artifacts, and record `model_version` and `threshold_set_version` on every score row.

**H4. Golden key derivation, survivorship and unmerge are undefined.**
- "Oldest key" doesn't say by what measure. A late-arriving older record could change the survivor.
- Links are "never deleted", but a steward split has no way to retire a link.
- Transitive closure can merge A~B and B~C where A must-not-link C.

*Fix (AD-13):*
- `golden_person_hk` = MD5 of a minted surrogate (`PERSON||<first-seen source hk>`), assigned once and never recomputed.
- Survivor = the earliest `HUB_PERSON.load_dts`, with ties broken by hk.
- Merge/split are insert-only effectivity satellites (`EFS_LINK_MEMBER_PERSON`, `EFS_LINK_PERSON_SAME_AS` with `is_active`, `decision_id`) on the links. Current state = the latest effectivity row.
- Must-not-link is checked on the whole candidate cluster after transitive closure and before any insert. It overrides auto bands, including scores of 0.90 or higher.
- A violation sends the case to the steward queue.
- `DIM_PATIENT` resolves through active same-as to the survivor.

**H5. The must-not-link store and steward decision contract aren't defined.**
*Fix (AD-2/AD-13):* `steward.decisions(decision_id uuid, pair_hk, decision {MATCH, NO_MATCH, MUST_NOT_LINK, SPLIT}, reason_code, free_text_flag, steward_os_user, host, decided_at, supersedes_decision_id)`, insert-only. MPI applies decisions idempotently by `decision_id` and records the `decision_id` on the resulting effectivity rows. The latest decision per pair wins.

**H6. PHI in ops, logs and test artifacts.**
- `ops.*.detail JSON`, `drift_report` profiles (top values, min/max), Spark cast-failure exceptions (which print the offending value), Dataproc driver logs in Cloud Logging, and dbt `--store-failures` / test output can all carry PHI.
- "PHI scan in CI" covers code and fixtures, not runtime output.

*Fix (Consistency: Logging / AD-10 / AD-14):*
- ops `detail` holds only counts, rates, column names, reason codes, `_line_ordinal`, never values.
- Drift profiling on PHI-tagged columns is limited to null rate, distinct count and length stats.
- Spark catches cast errors and logs ordinal + column only.
- dbt `store_failures` is off globally, or targets `restricted_phi` only.
- Add a Cloud Logging bucket with short retention and restricted access for Dataproc/Cloud Run logs.
- A runtime PHI canary: datagen plants marker values, and an e2e job greps logs, ops, and `gold_deid` for them and fails if found.

**H7. `gold_deid` de-identification stops at the person token.** Dates of birth/service, ZIP5, rare diagnoses and small cells re-identify people even when the key is tokenized.
*Fix (AD-14):* use a Safe-Harbor-style projection declared in config per column: dates → year (or month for service), age capped at 90+, ZIP → ZIP3 (000 for small ZIP3s), no free text, and small-cell suppression (<11) in dashboard aggregates. The Cloud Run dashboard requires IAM-authenticated invokers (no `allUsers`), and its SA has read on `gold_deid` only.

### Medium

**M1. Silver dedup by `_file_sha256` only.** A payer resend with a different filename but identical bytes, or a corrected resend with overlapping records, lands twice. Landing rejects a duplicate *name*, and the name includes the sha, but there is no explicit reject on sha alone.
*Fix (AD-3):* dedupe on `_file_sha256` regardless of name, which produces `rejected_duplicate`. Overlapping corrected resends are allowed into Silver, and the vault absorbs them by hashdiff. Document that Silver row counts aren't unique per business record.

**M2. Late-arrival details missing (AD-11).**
- The corrective successor insert must carry the *current* run's `load_dts`, not a backdated one. Otherwise monotonicity breaks.
- Rows with equal `applied_dts` need a total order: `(applied_dts, load_dts, _file_sha256, _line_ordinal)`.
- Claim versioning: a void (freq 8) arriving before its original claim must still resolve current status by sequence, not arrival order.

*Fix:* add these to the AD-11/AD-12 rules and golden scenario tests in `build_sat`.

**M3. Lineage stops at vault staging (AD-6).** Satellites keep only `record_source` + `load_dts`, so you can't trace back from Gold to the line.
*Fix:* sats and links carry `_file_sha256` + `_line_ordinal` (or a `_lineage_hk` into an `ops.line_lineage` mapping). MPI rows carry `run_id`, `model_version`, `decision_id`. Gold facts carry the PIT snapshot date. Add a dbt test that every Gold row reaches a Bronze line.

**M4. Open Question 4 (reconcile line hash).** Recommendation:
- Use SHA-256 over raw bytes per record, kept separate from the AD-7 business hash.
- Define the record splitting rule per format: X12 splits on the segment terminator from ISA16, not on newline, and `_line_ordinal` = segment ordinal. CSV is RFC-4180 aware, so embedded newlines are allowed. Strip the BOM.
- Bytes that aren't valid UTF-8 → store `_raw_line_b64` so fidelity stays provable.

**M5. The audit trail is append-only by convention only.** The runtime SA can `DELETE`/`UPDATE` ops and steward tables.
*Fix (AD-10):* use a separate `ops-writer` identity. Add a daily export of ops to a GCS bucket with a retention policy (bucket lock optional in the POC). Enable GCS Data Access audit logs on the landing and warehouse buckets (off by default). BigQuery data-access logs are on by default and should be kept. Add a CI/dbt test that row counts in ops tables never decrease between runs.

**M6. Steward app (local) pulls PHI to the dev container.**
*Fix:* no `st.cache_data` persistence to disk, no CSV export, the queue query is limited to the fields being compared, and the session runs as the user's impersonated steward SA. OS identity is recorded as-is; the spine should note that it can be spoofed in the POC (Phase 2: IAP).

**M7. MPI scratch and model artifacts contain PHI.** Splink DuckDB files, comparison vectors and XGBoost training frames hold names and DOBs. `SAT_MPI_MATCH_DETAILS` must store only gamma levels, match weights and probabilities, never compared values.
*Fix:* DuckDB runs in memory or in a tmp dir that is wiped on exit, and model artifacts go to a restricted bucket.

### Low

- **L1.** The HMAC key isn't scoped per client, and rotation isn't defined. *Fix:* one secret per client project (AD-19), versioned; the token table carries `key_version`. Rotation re-mints tokens into a new view version, and old tokens are never mixed with new ones.
- **L2.** Landing raw files are kept forever in Archive (the AD-3 override), which multiplies PHI copies (landing + Bronze `_raw_line` + Silver). Accept for synthetic data, but declare in AD-14 that each copy has the same restriction (runtime SA only) and the same CMEK-readiness.
- **L3.** Datagen must use reserved, non-real identifier ranges (SSN 9xx, test NPIs with a valid checksum but flagged synthetic) so that a leak is distinguishable and the canary in H6 works.
- **L4.** The quarantine state diagram has `quarantined --> reconciled` for every reason, but `RECONCILE_FAIL` can't be fixed by adding a mapping. It needs a `relanded` path (a new sha).

## Upstream PRD update needed (deliberate user overrides, not spine defects)

- dbt Fusion is the blocking build. Core is a non-blocking fallback (PRD prd:371).
- Landing lifecycle: Coldline at 7d, Archive at 60d, never deleted (PRD 7-day delete). The PRD's PHI retention language should also reflect the extra raw copy (L2).
- No Airflow by default. Local runner, with Workflows/Composer behind flags.
- Dataproc Serverless 3.0 / Spark 4.0 / Python 3.12.
- Bronze granularity is one table per (source, feed, era), not one per delivery.

## Proposed AD text deltas (summary)

| AD | Change |
| --- | --- |
| AD-2 | Add writers: token job → `restricted_phi.person_token`; Spark → `restricted_phi.<entity>_phi`; steward → `steward.decisions` (schema H5) |
| AD-4 | Iceberg WAP branch per sha; idempotent skip via `file_lifecycle` |
| AD-7 | Full normalization spec (H1); hashdiff not uppercased; all-null key rejected |
| AD-8/14 | PHI split or policy tags at Silver; PHI sats in `restricted_phi` |
| AD-10 | Separate ops writer, retention export, no values in `detail`, GCS data-access logs |
| AD-11/12 | Ordering tuple, non-backdated corrective inserts, void-before-original |
| AD-13 | Minted golden key, effectivity sats for merge/split, cluster-level must-not-link, deterministic reruns, model versioning |
| AD-14 | Token table instead of in-view HMAC; no `*_hk` in `gold_deid`; Safe-Harbor projection; authenticated Cloud Run; runtime PHI canary |
| AD-6 | `_file_sha256`/`_line_ordinal` carried into vault; Gold-to-line lineage test |
