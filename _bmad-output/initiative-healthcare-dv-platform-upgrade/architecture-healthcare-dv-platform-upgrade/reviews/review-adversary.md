# Adversarial Review — Architecture Spine (Healthcare DV Platform Upgrade)

Method: for each hole, two epics/features are built that each obey every AD literally, yet integrate incompatibly. Each hole closes with exact proposed AD text (new or tightened). Memlog decisions (later supersedes earlier) were treated as authority.

## Upstream PRD update needed (deliberate user overrides — NOT spine defects)

| Override | Spine | PRD says |
| --- | --- | --- |
| dbt Fusion blocking, Core non-blocking local fallback | AD-15 | Core blocking, Fusion non-blocking (prd:371) |
| Landing Standard -> Coldline 7d -> Archive 60d, never deleted | AD-3 | 7-day delete |
| No Airflow by default; local runner, Workflows/Composer flagged off | AD-16, AD-17 | Airflow-run assumption |
| Dataproc Serverless 3.0 (Spark 4.0, Py 3.12) | AD-21, Stack | earlier runtime / Py 3.11 implied |
| Bronze one table per (source, feed, era) | AD-4 | per-delivery / different granularity |

Note: the memlog also records the user's request for dbt *platform-login* features (lineage). The spine defers them, which matches a later memlog note that CLL works without login. No defect.

---

## Critical — integration breaks on the first run

### H1. The unmapped-era table name is written two ways
- **Epic A (Bronze loader)** follows AD-5 and writes `feed__unmapped-<fp8>`.
- **Epic B (drift and remap tooling)** follows the Conventions table and the data-flow diagram, which use `unmapped_<fp8>`. It finds no table to read.
- A hyphen is also not legal in a BigQuery or Iceberg identifier unless it is quoted.
- **Proposed AD-5 tightening:** "Unknown fingerprint -> era literal `unmapped_<fp8>`, where `<fp8>` is the first 8 lowercase hex characters of the fingerprint. Bronze table name `<feed>__unmapped_<fp8>`. Era literals match `^[a-z0-9_]+$`."

### H2. The fingerprint algorithm is not specified
- **Epic A (onboarding: datagen samples plus mapping YAML)** computes `sha256(header line)`.
- **Epic B (Bronze loader)** computes sha256 of the sorted, trimmed column list. For X12, it uses the segment-ID sequence.
- Each obeys AD-5 ("fingerprint of the header/segment layout"), but no mapping ever matches. Every file goes to `unmapped`.
- **Proposed new AD-22 (Fingerprint specification):** "The schema fingerprint algorithm per file format (delimited, fixed-width, X12, JSON) is defined once in `config/standards/fingerprint.yaml`, with golden vectors. It is implemented only in `config/` as `fingerprint(path) -> hex` and is used by the Bronze loader and by `make onboard`/validate-config. Mapping YAML stores the full lowercase hex fingerprint. No engine reimplements it."

### H3. Two writers of `ops`
- AD-2 says "Spark writes ... `ops`".
- The Layers table says `pipeline/` writes `ops` run events. AD-17 requires every task to be "resumable via `ops`", so dbt and MPI tasks must record state there.
- The `vault_loaded` lifecycle state can only be known after dbt runs.
- **Epic A (runner)** appends `ops.run_events`. **Epic B (dbt)** uses an on-run-end hook to append `file_lifecycle` with the state `vault_loaded`. **Epic C (Spark)** also writes `run_events`. Result: three writers with three row shapes.
- **Proposed AD-2 tightening:** "`ops.file_lifecycle`, `ops.quarantine` and `ops.drift_report` are written only by `ingestion/` (Spark plus the storage-class reconciler). `ops.run_events` is written only by the `pipeline/` runner (local, Workflows or Airflow renderers all call the same `pipeline.ops.emit()`). Downstream states (`vault_loaded`, `mpi_resolved`, `gold_published`) are appended by the runner after the invoked task succeeds. dbt and MPI never write `ops`."

### H4. No owner for `restricted_phi`
- AD-14 says PHI lives in `restricted_phi`, "joined by hash key", but AD-2 assigns it no writer.
- **Epic A (Spark Silver)** splits tagged PHI columns into `restricted_phi.<entity>` keyed on `_file_sha256 + _line_ordinal` (it has no hash key yet).
- **Epic B (dbt Raw Vault)** builds `restricted_phi.SAT_<parent>_PHI` keyed on `<entity>_hk`.
- The result is two owners, two keys, and Silver still holding PHI in the clear.
- **Proposed AD-14 tightening:** "Silver retains PHI-tagged columns (Silver dataset is runtime-SA only). dbt is the sole writer of `restricted_phi`: every PHI-tagged attribute is routed by `build_sat` into `restricted_phi.SAT_<PARENT>_PHI` keyed by `<entity>_hk` + `load_dts`. Non-PHI satellites in `raw_vault` never carry a PHI-tagged column. The routing is decided from config PHI tags only."
- Also add `restricted_phi` to AD-2's dbt list.

### H5. The steward queue has no owner, and steward decisions have no shape
- AD-2 says the steward app writes "only steward decision tables". The data flow shows "steward queue -> decision".
- **Epic A (MPI)** writes `steward.review_queue` (MPI is not listed as its writer, but nobody else is either).
- **Epic B (steward UI)** builds its own queue by querying `SAT_MPI_MATCH_DETAILS` where the score is under .95. Decisions are keyed on the pair `(person_hk_a, person_hk_b)` in one epic and on a `candidate_id` in the other.
- MPI cannot consume the decisions.
- **Proposed new AD-23 (Steward contract):** "MPI is the sole writer of `steward.review_queue` (one row per candidate pair: `candidate_id` = MD5 per AD-7 of sorted (`left_record_hk`, `right_record_hk`), scores, `run_id`). The steward app is the sole writer of `steward.decision` (`candidate_id`, `decision` in {MATCH, NO_MATCH, MUST_NOT_LINK}, `steward_id` = OS user, `decided_at` UTC TIMESTAMP), insert-only; latest `decided_at` per `candidate_id` wins. The next MPI run consumes decisions by `candidate_id`."

### H6. The state machine contradicts AD-4
- AD-4 says the reconcile gate "must pass before a file is marked `bronze_loaded`".
- The lifecycle diagram has the order `bronze_loaded -> reconciled | quarantined`.
- **Epic A (Bronze writer)** emits `bronze_loaded` before the gate. **Epic B (Silver)** follows AD-4 and treats `bronze_loaded` as "safe", so it reads files whose reconcile gate failed.
- **Proposed AD-4/AD-10 tightening:** "Lifecycle states are a closed enum in `config/standards/lifecycle.yaml`: `landed, rejected_duplicate, bronze_appended, reconciled, quarantined, silver_loaded, vault_loaded, mpi_resolved, gold_published`. Silver selects only files whose latest state is `reconciled` and that have no later `quarantined`. 'Latest' = max(`event_ts`, then sequence) per `file_sha256`."

### H7. Remapping an unmapped era: two incompatible recovery paths
- A file sits in `feed__unmapped_ab12cd34`, and a mapping is then added.
- **Epic A (rerun)** re-appends the file into `feed__v3` so Bronze matches the era naming. The rows now exist in two Bronze tables, which breaks the 1:1 proof.
- **Epic B** reads Silver from the unmapped table by applying the new mapping to it.
- Both follow AD-4/AD-5, since "never updated" forbids moving the rows.
- **Proposed AD-5 tightening:** "Bronze rows are never re-appended. A mapping entry binds one or more fingerprints to an era; Silver resolves `(source, feed, fingerprint) -> mapping` at normalize time and reads the file's rows from whichever Bronze table holds them, located via `ops.file_lifecycle.location`. `unmapped_<fp8>` tables are permanent."

---

## High — silent data corruption

### H8. Business-key composition and normalization order are not fixed
- **Epic A (dbt hub for `HUB_MEMBER`)** builds `payer_id||member_id`.
- **Epic B (MPI linking `LINK_MEMBER_PERSON`)** recomputes `member_hk` as `member_id||payer_id`, or casts dates differently before hashing.
- Both pass the AD-7 golden vectors, which test only the hash function and not the key recipe.
- EMR patients have no payer, so "payer-qualified" is undefined for `HUB_PATIENT`.
- **Proposed AD-7 tightening:** "`config/standards/business_keys.yaml` declares per hub the ordered BK columns, the qualifier column (`payer_id` for payer feeds, `source_system_id` for EMR) and per-column pre-hash canonicalization (dates `YYYY-MM-DD`, decimals no exponent/trailing zeros). Hashdiff column order = the satellite's config column list. MPI does not compute hub keys; it reads `<entity>_hk` from Raw Vault. Golden vectors cover each hub recipe."

### H9. How `golden_person_hk` is generated is undefined
- **Epic A** uses MD5 of the surviving member's `member_hk`.
- **Epic B** uses a UUID4 upper-hex.
- **Epic C (steward merge)** re-points to the oldest key.
- If the key is derived from a record, it collides with Raw Vault hash keys. AD-13 forbids that mixing but does not say how.
- **Proposed AD-13 tightening:** "`golden_person_hk` = MD5 upper-hex (AD-7) of the literal `PERSON||<first_contributing_record_hk>||<run_id>`, minted once and never recomputed. Merge never rewrites a key: it inserts `LINK_PERSON_SAME_AS(master_hk = oldest by first load_dts, duplicate_hk)`. Gold resolves through same-as to the master."

### H10. `load_dts` monotonicity versus reruns
- AD-6 says `load_dts` "derives from `_ingested_at`", and AD-11 needs `load_dts` monotonic.
- **Epic A** sets `load_dts = _ingested_at`. A quarantined file remapped weeks later still carries its original `_ingested_at`, so it lands behind newer satellite rows.
- **Epic B** sets `load_dts = CURRENT_TIMESTAMP()` of the dbt run. That breaks rerun idempotence and duplicates hashdiffs.
- **Proposed AD-6 tightening:** "`_ingested_at` = UTC instant the landing object was accepted (set once). `load_dts` = the `event_ts` of the file's `silver_loaded` lifecycle row (stable across reruns because Silver rerun is a no-op). Satellites compare on `load_dts`; ordering of late files is handled only by AD-11 XTS logic."

### H11. The scope of `run_id` is ambiguous
- AD-6 says `_run_id` is set at landing and never restamped. AD-13 says MPI writes "insert-only per run_id".
- **Runner epic** mints one `run_id` per pipeline invocation. **MPI epic** mints its own.
- **dbt epic** reads `_run_id` from Silver to scope incremental loads, so it misses files landed in an earlier run.
- **Proposed new AD-24 (Run identity):** "`run_id` (format per Conventions) is minted only by the `pipeline/` runner per invocation and passed to every task as `PIPELINE_RUN_ID`. `_run_id` on data = the run that landed the file and is never used to select work. Work selection uses `ops.file_lifecycle` state only. MPI rows carry the invoking `run_id`."

### H12. Config merge semantics: Terraform and Python can disagree
- **Epic A (infra)** runs `yamldecode` on both files and uses `merge()`, which is shallow.
- **Epic B (loader)** deep-merges.
- A client override of `caps.bytes_billed.dbt` wipes all of `caps` in Terraform, so Terraform and Spark see different caps.
- **Proposed AD-1 tightening:** "`config/loader.py` is the only merger (deep merge, lists replace, client overrides defaults) and writes `config/build/<client>.resolved.json` (validated). Terraform reads only the resolved JSON via `jsondecode(file())`; dbt vars are generated from the same artifact at build time and never committed. A CI check fails if the resolved file is stale."

### H13. Flag key drift
- The Conventions table says `<service>_enabled`. The deploy diagram writes `looker`, `dataproc_schedule`, `workflows`, `composer`.
- **Infra epic** writes `flags.dataproc_schedule_enabled`. **Runner epic** reads `dataproc_enabled`.
- **Proposed tightening (Conventions plus AD-16):** "Flags live under a single `flags:` map in `defaults.yaml` with keys exactly: `workflows_enabled, composer_enabled, looker_enabled, dataproc_schedule_enabled, dataproc_enabled`. JSON Schema sets `additionalProperties: false` on `flags`."

### H14. Timestamp and date typing
- The Conventions table says "all TIMESTAMP in UTC", but `applied_dts` is a "per-entity business date".
- **Silver epic** stores `service_date` as DATE. **dbt epic** casts it to TIMESTAMP at local midnight.
- PIT windows (AD-11) then shift by the timezone offset.
- **Proposed tightening:** "`applied_dts` is TIMESTAMP UTC; a source DATE becomes `TIMESTAMP(date, 'UTC')` at 00:00:00 in Spark Silver normalization; source local datetimes without a zone are interpreted in the source's `timezone` declared in the mapping YAML (required). No engine re-casts."

### H15. Silver entity names and the claim-line shape
- AD-8 lists `claims (+lines)`, `remittance_835`, `pharmacy`. The Conventions table says "singular snake_case".
- **Spark epic** creates `silver.claim` with nested lines. **dbt epic** sources `silver.claims` and `silver.claim_line`.
- **Proposed AD-8 tightening:** "Canonical Silver tables, exactly: `silver.claim`, `silver.claim_line`, `silver.eligibility`, `silver.remittance_835`, `silver.pharmacy_claim`, `silver.provider`, `silver.patient`, `silver.encounter`; the list lives in `config/standards/entities.yaml` with each entity's target hubs (e.g. `pharmacy_claim -> HUB_RX_CLAIM`, `eligibility -> HUB_COVERAGE`)."

---

## Medium

### H16. Who owns data drift
- AD-9 says data drift warns at Silver and blocks at Gold.
- **Spark** writes `ops.drift_report`. **dbt** recomputes drift as tests with different thresholds (D-7 is deferred).
- **Proposed tightening:** "Data-drift metrics are computed only by Spark into `ops.drift_report` with thresholds from config. The Gold publish gate is a dbt test that reads `ops.drift_report` (declared as a source) and fails on any `DATA_DRIFT` severity=block row for the run's files."

### H17. The reconcile line hash (Open Question 4)
- **Bronze writer** stores the MD5 per AD-7, which uppercases and trims. **Reconciler** uses sha256 of the raw bytes.
- The reconcile gate then always fails, or always passes if both trim.
- **Proposed AD-4 tightening:** "Line hash = sha256 lowercase hex of the raw line bytes excluding the terminator, no normalization; AD-7 MD5 applies to vault keys only."

### H18. The quarantine row granularity is ambiguous
- The quarantine shape has a per-column `column` and `failure_rate`.
- **One epic** writes one row per file. **Another** writes one row per failing column. Release logic then counts differently.
- **Proposed tightening:** "One `ops.quarantine` row per (file_sha256, reason_code, column); `column` null for file-level reasons. A file is quarantined iff its latest lifecycle state is `quarantined`; quarantine rows are diagnostic only."

### H19. Bronze "dataset" versus namespace
- AD-14 restricts "the Bronze bucket and dataset". Conventions only define the REST namespace `bronze_<source>`.
- **Infra epic** creates a BQ dataset `bronze` for BigLake external access. **Ingestion epic** expects `bronze_<source>` datasets.
- **Proposed tightening:** "BigQuery sees Bronze only via namespace-mirrored datasets `bronze_<source>` created by Terraform from the source list in config; IAM: runtime SA only."

## Summary of proposed changes

New: AD-22 Fingerprint spec, AD-23 Steward contract, AD-24 Run identity.

Tightened: AD-1 (resolved JSON), AD-2 (ops split, restricted_phi), AD-4 (state enum, line hash), AD-5 (literal, remap path), AD-6 (load_dts source), AD-7 (BK recipes), AD-8 (entity names), AD-9/AD-16 (drift owner, flags), AD-13 (golden key minting), AD-14 (PHI routing, Bronze datasets), plus the timestamp convention.
