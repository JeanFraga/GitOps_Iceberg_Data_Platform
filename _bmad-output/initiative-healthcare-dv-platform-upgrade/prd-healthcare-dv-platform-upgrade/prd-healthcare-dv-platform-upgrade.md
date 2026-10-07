---
title: Healthcare Data Vault Platform Upgrade
status: final
created: 2026-10-07
updated: 2026-10-07
---

# PRD: Healthcare Data Vault Platform Upgrade
*Initiative slug: `healthcare-dv-platform-upgrade` (confirmed).*

## 0. Document Purpose
This PRD is for the repo owner, who builds and maintains it. It is also for the architecture, ticketing and build workflows that come after it. It turns the target healthcare Data Vault 2.0 architecture into capabilities that can be tested. It does not specify how they are built. Technology choices, the target repo layout, the architecture diagram, tool trade-offs and research figures are in `addendum.md`, next to this file. The current state comes from the POC findings: the repo today is a working NYC Taxi medallion POC on GCP. All domain terms are defined in §3, and the rest of the document uses them exactly as defined. Features are grouped in §4, with globally numbered FRs nested under each one. Cross-cutting NFRs are in §5. Anything inferred without confirmation is tagged `[ASSUMPTION]`, and every tag is listed in §12.

**Companions:** the final architecture spine `_bmad-output/initiative-healthcare-dv-platform-upgrade/architecture-healthcare-dv-platform-upgrade/architecture-healthcare-dv-platform-upgrade.md` (decisions AD-1 to AD-25, Stack, diagrams, source tree). Where this PRD was updated on 2026-10-07 to align with it, the spine is the source of the change.

## 1. Vision
The project turns the repo from a taxi demo into an end-to-end **healthcare data platform** and proves three things. Data Vault 2.0 can absorb messy feeds from several payers and several schema eras. dbt can build that vault natively on GCP, with the dbt Fusion engine ("dbt 2.0") as the only blocking build (SM-8). The whole thing can run, from synthetic source files to a Gold star schema with a Master Patient Index, **for under USD 5 in total** (user-stated budget, confirmed), staying in the free tier wherever practical, with expensive always-on services off by default, built from the dev container CLI and deployed by GitHub Actions.

All data is synthetic. A seeded, deterministic generator produces feeds shaped like real healthcare feeds: 834 eligibility, 837P/I/D submitted claims, 835 remittances, pharmacy claims and FHIR R4 patients and encounters. It deliberately injects schema drift, data drift and identity noise, and it keeps the ground truth. Because the truth is known, the platform can **measure** how well it resolves identities instead of just claiming it does. That measured result is the main thing the portfolio shows.

The project is also a **framework for clients**. Onboarding a new payer or a new schema era should take configuration (a mapping file and a canonical schema reference), not code. The pipeline is declared once as a single DAG specification. A local runner executes it by default at no cost, and the same specification can be rendered for a managed scheduler or for Airflow on Cloud Composer for a production client, behind flags, without rewriting any step.

## 2. Target User

### 2.1 Jobs To Be Done
- **Portfolio owner (functional and social):** show credible, senior-level command of DV 2.0, dbt, GCP, entity resolution and healthcare data patterns in a repo that a reviewer can clone and run.
- **Data engineer at a client (functional):** onboard a new payer feed or schema era by writing configuration, and get a drift report rather than a broken pipeline.
- **Data steward (functional):** review uncertain identity matches, decide them, and know that the decisions improve the next run.
- **Analyst or data scientist (functional):** query patient-level claims and encounters through one golden patient key, without needing to understand the vault.
- **Future client buyer (contextual):** see that the design ports to production (managed orchestration, Dataproc) without a rewrite, with an open-format (Apache Iceberg) raw layer already in place.

### 2.2 Non-Users (v1)
- Clinical end users, members or patients. There is no patient-facing surface.
- Anyone handling **real PHI**. The POC must never ingest real data.

### 2.3 Operator Scenarios
- **UJ-1. A data engineer onboards Payer C.** Dana has a sample of Payer C's 837P CSV. She adds a mapping file for Payer C's era and points it at the canonical claims schema. She runs the mapping validator locally, which flags two unmapped source columns and one column that will not cast. She fixes the mapping and opens a PR. CI validates the configuration, runs the pipeline on a small synthetic slice and publishes a drift report. After the merge, Payer C records appear in the hubs with their own record source, and no model code changed. **Edge case:** a 2024 file arrives with a new column. The pipeline identifies the file's schema era by its schema fingerprint. Because the layout only adds columns to a mapped era, the file goes to that era's Bronze table, the new column is reported as drift, and Silver loads with canonical columns padded to defaults; the run does not fail. A file whose layout matches no mapped era (not additive-only) lands in an unmapped-era Bronze table and is quarantined at Silver until Dana adds a mapping, after which it is replayed without re-landing.
- **UJ-2. A data steward resolves an HITL match.** Sam opens the steward queue and sees a pair with a match score of 0.72: same DOB and address, different first names. These are likely twins. The ML fallback also scored the pair below 95%. Sam looks at the claims and visit context side by side and marks the pair "not a match", with a reason. The decision is stored with Sam's identity and a timestamp. On the next MPI run, the pair is not sent to the queue again, and the decision becomes a labeled training example. **Edge case:** if two stewards disagree on the same pair, the most recent decision wins, both decisions stay in the audit trail, and the pair is flagged for a second review.

## 3. Glossary
- **Payer feed:** a file-based extract from a health plan. It is an eligibility feed (ANSI 834 style), a claims feed (837P professional, 837I institutional, 837D dental) or a pharmacy feed (NCPDP style).
- **EMR feed:** patient and encounter data from a facility in HL7 FHIR R4 form (Patient, Encounter, Condition, Procedure), shaped on US Core profiles.
- **Member:** a person enrolled with one payer, identified by `payer_id + subscriber_id + person_code`. Subscriber IDs are unique only within a payer and are shared by dependents; the person code tells household members apart.
- **Patient:** a person known to one EMR system, identified by `emr_system_id + MRN`. A patient is not a member; the MPI resolves members and patients together into persons.
- **Claim / claim line:** a claim header (837 CLM) and its service lines (LX/SV1/SV2/SV3). A claim can have several versions (837 frequency code 1 original, 7 replacement, 8 void; 835 adjustments); the latest effective version is the one counted.
- **Coverage span:** one eligibility period for a member under one product line (Commercial, Medicaid, Medicare) and plan, with effective and term dates.
- **Source:** a single payer feed or EMR feed from one named sender, such as Payer A, Payer B or EMR Facility 1.
- **Schema era:** a version of one source feed's layout (for example, Payer A claims 2022–2023). A source has one or more schema eras. A file's era is identified by its schema fingerprint, not by its date.
- **Schema fingerprint:** a deterministic hash of a file's header or segment layout, computed the same way by the Bronze loader and the onboarding tooling. Configuration maps fingerprints to eras; an unknown fingerprint creates an unmapped era. A fingerprint whose columns only add to a mapped era's columns maps to that era (additive rule).
- **Mapping:** a versioned configuration file that projects one schema era of one source onto a canonical schema. Each pair of source and schema era has exactly one mapping.
- **Canonical schema:** the standard Silver contract for one entity type. There are eight: claim, claim_line, eligibility, remittance_835, pharmacy, provider, patient and encounter.
- **Landing zone:** immutable storage where source files are kept byte-for-byte as received, under content-hashed names. Files move to colder storage classes over time and the pipeline never deletes them; POC teardown deletes them (regenerable).
- **Processing log (file lifecycle):** an append-only record of every file's state as it moves through the pipeline (landed, appended to Bronze, reconciled, loaded to Silver, loaded to the vault, or rejected as duplicate or quarantined) and of each run's events. Stages find their work from it.
- **Quarantine:** the state of a file that failed reconciliation, has an unmapped era, or exceeded a cast-failure threshold. Its rows stay in Bronze and do not reach Silver until the cause is fixed and the file is replayed.
- **Bronze:** a queryable 1:1 raw replica of the landing zone, stored as one Apache Iceberg table per (source, feed, schema era), written by Spark and queryable from BigQuery. Each delivery is appended once and never updated or deleted; Bronze is never expired during the POC (POC teardown deletes it; it is regenerable) and becomes the queryable system of record once a file passes reconciliation. Flat files expose every column as a string; nested files (FHIR NDJSON, EDI-derived JSONL) expose one JSON string column per record. File lineage is kept. Bronze is the only Iceberg layer; Silver and everything downstream are native BigQuery tables.
- **Silver staging:** canonical, typed and normalized records produced by the mapping engine.
- **Drift:** any difference between an incoming file and its mapping: a new, missing or renamed column, or a value that fails to cast. Also called schema drift.
- **Data drift:** a change in the values or distribution of a column while its schema stays valid, such as a shifted code mix, a changed null rate, a unit or scale change, or a shifted amount distribution.
- **Sample file:** a committed 1,000-record excerpt of one generated feed file, kept in the repo for tests and review. Full-size files are never committed.
- **Drift report:** the record of drift for each file that a normalization run produces.
- **Raw Vault:** hubs, links and satellites loaded from Silver staging with no business rules applied.
- **Hub / Link / Satellite:** the standard DV 2.0 objects. They hold business keys, relationships, and descriptive history (SCD2), respectively.
- **Record source:** a lineage tag on every vault row that names its source and schema era.
- **Business Vault:** derived vault objects. These are the MPI results, computed claim attributes and PIT tables.
- **MPI (Master Patient Index):** the process and the output that resolve member and patient records into golden keys.
- **Golden person key:** the surviving master identifier for a resolved person, held in `HUB_PERSON` (`golden_person_hk`) and linked to both payer members and EMR patients. It is owned by the MPI and kept separate from Raw Vault hash keys. "Golden key" and "member key" in Gold clustering mean this key.
- **Match score:** the calibrated `match_probability` of a candidate pair (not the raw match weight). Calibration is checked against a held-out ground-truth slice.
- **Match band:** the tier a candidate pair falls into by match score, as half-open intervals: new golden key [0, 0.50), edge case [0.50, 0.90), auto-match [0.90, 1.00].
- **Must-not-link:** a constraint (from a steward "no match" or a configured rule) that forbids two records from sharing a golden key, even through transitive closure.
- **Training seed / evaluation seed:** two disjoint generator seeds with separate noise scenarios. Models are tuned and trained only on the training seed; reported metrics come only from the evaluation seed.
- **ML fallback:** the second-stage classifier that scores edge-case pairs using context beyond demographics.
- **Steward queue:** the edge-case pairs that the ML fallback could not auto-match (ML score in [0, 0.95)), waiting for a human decision.
- **Steward decision:** a human verdict on one queued pair (match, no match, must-not-link, unmerge or defer), with who, when and why.
- **Ground truth:** the generator's record of which synthetic records belong to the same true person.
- **Gold:** a star schema and denormalized analytic tables keyed on the golden key. Consumers (dashboard, extracts) read Gold directly in the POC.
- **Future Enhancement phase:** designed but not built work, kept out of Phase 1 and Phase 2 until a named trigger occurs (§8.4): PHI hardening and the Atmos configuration layer.
- **Client profile:** the set of configuration that defines one client deployment: sources, mappings, environment and cost limits.
- **Run:** one end-to-end or partial execution of the pipeline for a period, identified by a run ID.

## 4. Features

### 4.1 Synthetic Healthcare Data Generation
**Description:** A seeded, modular generator (pluggable per feed type, source and drift scenario) creates a realistic population with eligibility spans, claims, pharmacy claims, remittances, EMR patients and encounters, and providers for at least two payers and one facility. By default it produces 2 years of files at 30,000 records per file. Its output matches each source's schema era. It deliberately introduces schema drift (5 scenarios by default), data drift and identity noise, and writes the ground truth. Volume is controlled by configuration (`.env`). Full-size files are generated on opt-in Dataproc runs and are never committed; the repo holds only 1,000-record sample files and a README on how files are generated. Every output is labeled synthetic. [ASSUMPTION: the synthetic X12 is simplified and does not claim standards certification.]

#### FR-1: Deterministic population generation
The operator can generate a population of persons, members (with subscriber/dependent households), coverage spans, providers, claims (P/I/D), 835 remittances, pharmacy claims and FHIR patients and encounters from a seed and size parameters.
**Consequences:**
- The same seed and parameters produce identical content: the SHA-256 of each dataset's records, sorted by a declared key, is equal across runs (file names, partition counts and timestamps may differ).
- Size parameters are read from the client configuration (`volume_profile`): records per file (default `30000`) and the span of files (default 2 years of periodic files per feed). `.env` may override them locally only; on conflict the configuration wins. Changing them needs no code change.
- The generator is modular: each feed type, source and drift scenario is a separate pluggable component registered in configuration, so a new feed or scenario is added without editing the others.
- A separate "CI volume" profile [ASSUMPTION: about 5k members] exists for in-runner end-to-end tests; the default volume is for full runs.
- Full-size default runs execute on opt-in Dataproc (FR-12) and write directly to the landing zone.
- Every output carries a synthetic-data marker in its file metadata or name.

#### FR-2: Source-shaped output per schema era
The generator writes each source in that source's native format and schema era. The formats are X12-structured 834 and 837, flat payer CSV variants, NCPDP-style pharmacy CSV, and FHIR NDJSON.
**Consequences:**
- Files cover a 2-year window by default (configurable). Payer A emits two claims schema eras whose column names differ, with the era boundary inside the window.
- Payer B and EMR Facility 1 each emit at least one schema era.
- Payer claims cover 837P and 837I with claim-type-specific nullable sections (837I: type of bill, admit/discharge dates, revenue codes, DRG), 837D, and an 835 (or adjudicated flat extract) carrying allowed, paid, patient-responsibility (CAS PR) amounts and adjudication status. X12 shapes reference 005010X220A1 (834), X222A1 (837P), X223A2 (837I), X224A2 (837D) and X221A1 (835), not certified.
- 834 output includes maintenance codes (INS03 021 add, 024 term, 001 change), full and change files, and plan switching between payers with coverage gaps.
- Claim versions are generated: originals, replacements (frequency 7) and voids (frequency 8).
- FHIR Encounters reference Patient, Practitioner and Organization. Encounters do not carry a claim ID; the encounter-to-claim link appears only in the ground truth.
- Codes use real code-system shapes. ICD-10-CM/PCS and HCPCS Level II may use public CMS files. CPT and CDT codes are generated code-shaped values with no AMA/ADA descriptors or real code lists. NPIs carry a valid Luhn check digit (prefix 80840). NDCs are emitted in 10-digit 4-4-2, 5-3-2 and 5-4-1 forms.

#### FR-3: Deliberate drift injection
The operator can turn schema drift scenarios on. Five scenarios ship by default: renamed columns, new columns added mid-era, removed columns, changed date formats, and values that fail to cast.
**Consequences:**
- Each drift scenario that is injected is listed in a generator manifest (scenario, source, file, first affected record) so that tests can assert it was detected.
- Each scenario is a pluggable generator component; adding a sixth scenario needs no change to the existing ones.

#### FR-4: Identity noise and ground truth
The generator injects identity noise and records the ground truth for it. The noise types are typos, nicknames, swapped names, transposed day and month in the DOB, twins at a shared address, address moves, SSN missing or last four digits only, last-name changes, hyphenated and compound surnames, name-order swaps, newborns with placeholder names ("BABY GIRL SMITH") on the mother's member ID, Jr/Sr at one address, shared or default SSNs (999-xx-xxxx, 123-45-6789), households sharing subscriber ID, address and phone, and cross-payer plan switching.
**Consequences:**
- A ground-truth table maps every source member and patient record to a true person ID.
- The edge-case rate is defined as the share of true-match record pairs that carry at least one edge-case noise type. It is configurable; the default is 2% ± 0.5 percentage points. [ASSUMPTION]
- The evaluation seed uses at least one noise scenario not present in the training seed.

#### FR-36: Data drift samples
The generator can inject data drift, where schema stays valid but values shift: a changed code mix (for example diagnosis or place-of-service distribution), a changed null rate on a column, a unit or scale change in an amount, and a shifted billed or paid amount distribution.
**Consequences:**
- Each data drift scenario is a pluggable component, listed in the generator manifest with the affected source, column, file and expected shift.
- At least one data drift sample is present in both the default run and the committed sample files.
- The normalization run reports per-file column profiles (null rate, distinct-value share, numeric mean and percentiles) and flags shifts above a configured threshold against the previous files of the same source and era. Data drift is always reported; it blocks Gold publication only when thresholds are configured (NFR-5), and never blocks Silver.

#### FR-37: Sample files and generation README
The repo commits only small sample files and documents how full-size files are produced.
**Consequences:**
- Each feed has one committed sample file of 1,000 records, generated by the same generator and seed and carrying the synthetic marker; at least one sample shows a schema drift scenario and one shows a data drift scenario.
- A README explains the generator modules, the configured size settings (`volume_profile`, records per file, default 30000, with `.env` as a local override only), how to run locally and on Dataproc, and how to regenerate the sample files.
- CI fails if a generated data file larger than the sample size, or any file above a configured size limit, is committed outside the sample folder.

### 4.2 Immutable Landing and Bronze Raw Replica
**Description:** Source files land unchanged in an immutable zone under unique, content-hashed object names; they are tiered to colder storage over time and the pipeline never deletes them (POC teardown does). Bronze copies every landed file 1:1 into one Apache Iceberg table per (source, feed, schema era), written by Spark and queryable from BigQuery, and proves the copy against the landing object before downstream use. Every column is a string, original headers are kept, and the file name and ingestion timestamp are attached. Every file's progress is recorded in the processing log. EDI files are kept raw in landing. For Bronze queryability, a line-oriented representation of each file is derived and preserved alongside it.

#### FR-5: Immutable landing
Each file lands with a path that records source, ingestion date and a content hash, so every object name is unique. Once landed, a file cannot be overwritten, and the pipeline never deletes it.
**Consequences:**
- Re-delivering a file with the same source name lands as a new object; an attempt to overwrite an existing object is rejected and logged. A file whose content hash was already processed is recorded as a rejected duplicate and not reloaded.
- Landing objects move to a colder storage class after 7 days and to an archive class after 60 days, and the pipeline never deletes them. No retention lock is applied; at POC teardown `terraform destroy` deletes the landing bucket and its objects (force_destroy), since all data is regenerable from the seeded generator; Coldline/Archive early-deletion charges are accepted, and production adds a delete lock and retention policy (§8.4).
- Every lifecycle transition (landed, appended to Bronze, reconciled, loaded to Silver, loaded to the vault, rejected duplicate, quarantined) and every observed storage-class move is appended to the processing log, so the whereabouts and state of every file are known.

#### FR-6: Bronze raw replica
An analyst can query each landed file as rows in the Bronze Iceberg table for its (source, feed, schema era). A Spark job writes the tables; BigQuery reads them. For flat files every column is stored as a string and original headers are kept; nested files (FHIR NDJSON, EDI-derived JSONL) are one JSON string column per record. The source file name, content hash, record ordinal and an ingestion timestamp are stored as columns; tables are partitioned by ingestion date.
**Consequences:**
- A file's era is identified by its schema fingerprint. An unknown fingerprint lands in an unmapped-era table and is reported as drift; an additive-only layout lands in its mapped era's table.
- Each delivery is appended once as an Iceberg snapshot tagged with the run ID and file hash; reloading the same file appends nothing. Rows are never updated or deleted, and Bronze has no expiration. At POC teardown, `terraform destroy` deletes the Bronze tables and their storage, since all data is regenerable from the seeded generator; production adds a delete lock (§8.4).
- A reconcile gate checks record count and a per-record hash against the landing object before the delivery becomes visible; only reconciled files reach Silver, and a failure quarantines the file.
- Bronze can be pruned by ingestion date.
- No type coercion or column renaming happens in Bronze.
- Bronze is the only Iceberg layer. Silver staging and all vault and Gold tables are native BigQuery tables, because the dbt Fusion engine has no native Iceberg support.

#### FR-7: Raw-to-queryable pre-parse for EDI
EDI X12 files get a derived, line-oriented representation. The raw EDI file stays untouched in landing.
**Consequences:**
- The derived representation names the raw file it came from and has at least one record per segment, carrying interchange, functional group and transaction set control numbers, the segment ID, its ordinal position and its elements.
- Regenerating it from the same raw file produces byte-identical output; CI checks this on the sample files.

### 4.3 Config-Driven Silver Normalization
**Description:** A normalization engine reads Bronze Iceberg tables and one mapping for each combination of source and schema era. It applies standard column names (for example, `MBR_NO` becomes `member_id`), casts with a safe "try" approach, resolves drift, and pads missing canonical columns with defaults. It writes canonical Silver staging as native BigQuery tables, and a drift report. Supporting a new source or schema era requires only configuration.

#### FR-8: Mapping and canonical schema registry
The engineer can declare canonical schemas and mappings as versioned configuration files.
**Consequences:**
- A validator rejects a mapping that targets columns not in the canonical schema, or that is missing a required canonical column without declaring a default.
- Mapping validation runs in CI on every PR. Realizes UJ-1.

#### FR-9: Era-aware mapping selection
For each file, the engine picks the mapping by source, feed and the schema era identified by the file's schema fingerprint (FR-6), not by the file's date.
**Consequences:**
- A file whose era has no mapping is quarantined and reported. It is not silently dropped.
- A layout that only adds columns to a mapped era uses that era's mapping, with the extra columns reported as drift; the file is not quarantined.
- A quarantined file can be replayed through Silver after a mapping fix, without re-landing it or re-appending it to Bronze.

#### FR-10: Safe typing and default padding
Values that fail to cast become null. The original value is kept in Bronze, and the failure is counted in the drift report. Canonical columns with no source column get the mapping's default.
**Consequences:** a cast error does not fail the run. If a column's cast-failure rate is above a threshold set in the mapping, the whole file is quarantined and none of it reaches Silver. [ASSUMPTION: the default threshold is 5%.]

#### FR-11: Drift report
Every normalization run writes a drift report for each file. The report lists unmapped source columns, missing expected columns, cast-failure counts and the mapping version used.
**Consequences:** each scenario in the FR-3 manifest shows up in the drift report.

#### FR-12: Interchangeable Spark runtime
The same normalization and generator jobs run on a local Spark runtime and on a managed serverless Spark runtime. A configuration switch chooses between them, and the code does not change.
**Consequences:**
- CI and scheduled end-to-end runs use the local runtime on the GitHub-hosted runner (free tier).
- Managed runs on Dataproc are opt-in, manually triggered and capped in number per POC (at most 10 runs, confirmed; the runner refuses runs past the cap), with a per-run cost ceiling in configuration. Full-size data generation (FR-1) is one of these runs. Scheduled Dataproc runs are behind a flag that is off by default.
- A TTL guard tears the Dataproc capacity down after each run.
- The local runtime uses the same Spark, Java, Python and Iceberg versions as the managed runtime.

### 4.4 Raw Data Vault
**Description:** dbt models load Silver staging into a DV 2.0 Raw Vault. Stage models compute hash keys, hashdiffs, load date and record source. The vault contains `HUB_MEMBER` (payer-qualified member), `HUB_PATIENT` (EMR-system-qualified patient), `HUB_PROVIDER` (NPI), `HUB_CLAIM`, `HUB_CLAIM_LINE`, `HUB_PHARMACY_CLAIM`, `HUB_COVERAGE`, `HUB_VISIT`; `LINK_MEMBER_CLAIM`, `LINK_CLAIM_LINE`, `LINK_CLAIM_PROVIDER`, `LINK_MEMBER_COVERAGE`, `LINK_MEMBER_PHARMACY_CLAIM`, `LINK_PATIENT_VISIT`, `LINK_VISIT_PROVIDER` (encounter practitioner/facility NPI, FR-32); and `SAT_MEMBER_DEMOGRAPHICS`, `SAT_MEMBER_SENSITIVE` (SSN; tagged PHI), `SAT_PATIENT_DEMOGRAPHICS`, `SAT_CLAIM_HEADER`, `SAT_CLAIM_VERSION` (frequency code and sequence), `SAT_CLAIM_LINE`, diagnosis and procedure child satellites of the claim line, `SAT_CLAIM_ADJUDICATION` (835), `SAT_PHARMACY_CLAIM`, `SAT_COVERAGE`. `LINK_VISIT_CLAIM` is a derived rule and lives in the Business Vault (§4.7). Silver feeds the vault from eight canonical entities: claim, claim line, eligibility, remittance (835), pharmacy, provider, patient and encounter. Loads are insert-only and incremental, and late or out-of-order records are absorbed without reprocessing. Satellites keep SCD2 history.

#### FR-13: Deterministic hashing and staging
Stage models produce hash keys and hashdiffs with a single hashing standard set in configuration (decided: MD5 as uppercase hex STRING, portable across warehouses; FARM_FINGERPRINT is excluded). Every engine that computes keys (Spark, dbt, MPI) implements the same standard and passes shared golden test vectors in CI. Business keys are normalized before hashing (trimmed, upper-cased, with a configured delimiter and null sentinel). Business keys carry their assigning authority: payer-feed keys are qualified by payer ID and EMR-feed keys by EMR system ID. Members are `payer_id + subscriber_id + person_code`, patients `emr_system_id + MRN`, claims `payer_id + claim_id`, claim lines `claim key + line number`, pharmacy claims `payer_id + Rx number + fill number + pharmacy NPI + date of service`.
**Consequences:**
- The same qualified business key from two loads produces the same hub hash key.
- The same raw subscriber ID from two different payers, or the same MRN from two EMR systems, produces two different hub hash keys; cross-payer identity is resolved only by the MPI.

#### FR-14: Hubs, links and satellites
The Raw Vault loads the hubs, links and satellites listed above. Every row carries a load date and a record source. All vault tables are native BigQuery tables.
**Consequences:**
- Reloading the same Silver data adds zero rows (the load is idempotent).
- A changed demographic attribute adds exactly one new satellite row.
- SSN is stored only in `SAT_MEMBER_SENSITIVE`, its columns carry a PHI tag in configuration, and it is not part of any other satellite's hashdiff. Moving it to a restricted dataset is Future Enhancement work (§8.4).
- Replacements and voids of a claim share the claim's hub key; versions are tracked in a satellite, not as new claims.
- A record that arrives late or out of order is inserted with its own load date and business date, and the current-state view is still correct, without reprocessing earlier loads.
- dbt tests check uniqueness of hub keys and referential integrity of links to hubs.

#### FR-15: Vault package independence
The vault builds through small in-house macros (hash, hub, link, satellite) that run on the dbt Fusion engine. A standard DV package is an optional, time-boxed spike, not a second build path.
**Consequences:** the in-house macros build the full Raw Vault on the reference dataset on dbt Fusion; if the package spike runs, its row-count and hash-key differences are documented, not required to be zero.

### 4.5 Master Patient Index (Business Vault)
**Description:** A probabilistic (Fellegi-Sunter) model scores candidate member and patient pairs on demographics. Pairs with a match score in [0.90, 1.00] auto-match. Pairs in [0, 0.50) get a new golden key. (The match bands are thresholds; the quality targets in SM-1 are separate.) Edge cases [0.50, 0.90) go to an ML fallback that uses claims history, visit proximity (patient + date of service + NPI + facility) and provider patterns. ML scores in [0.95, 1.00] auto-match, and everything else goes to the steward queue. Results are stored in the MPI-owned Business Vault tables: `HUB_PERSON` (golden person key), member-to-person and patient-to-person links, the person same-as link and `SAT_MPI_MATCH_DETAILS`. The MPI is the only writer of these tables. Thresholds are configuration.

#### FR-16: Probabilistic demographic matching
The MPI scores blocked candidate pairs from `SAT_MEMBER_DEMOGRAPHICS` and `SAT_PATIENT_DEMOGRAPHICS` and assigns each pair a match band by calibrated match score.
**Consequences:**
- Thresholds come from configuration, not code, and are selected on the training seed.
- Each run reports blocking recall: the share of true-match pairs that survive blocking.
- Scores are written back insert-only per run; readers see only runs marked complete, so a partial write-back leaves the previous results in effect.
- Each scored pair records its score, method and model version.

#### FR-17: ML fallback for edge cases
Edge-case pairs are rescored with non-demographic context. Pairs that reach the ML threshold auto-match. The rest go to the steward queue.
**Consequences:**
- The ML step can be turned off. When it is off, every edge case goes to the steward queue.
- The model trains only on training-seed ground truth (later also steward decisions), split by true person ID so no person appears in both train and test. It is never trained on evaluation-seed data, including steward decisions made on evaluation-seed pairs.
- Ground truth is used only as labels, never as a model feature.
- Every trained model version is kept and identifiable, so earlier versions can be restored.
- The model runs locally (XGBoost); BigQuery ML is not used in the POC.

#### FR-18: Golden key assignment and same-as links
Every member record and every EMR patient record resolves to exactly one golden person key in `HUB_PERSON`, recorded through member-to-person and patient-to-person links and the person same-as link.
**Consequences:**
- Matches are transitive: if A=B and B=C, all three share one golden key.
- Golden keys stay stable across reruns unless new evidence or a steward decision changes the cluster. Every change is recorded.
- Must-not-link constraints are enforced during closure: an edge that would join two records under a must-not-link is dropped and logged. Must-not-link is also checked on the full cluster after transitive closure and overrides auto bands. Clusters above a configured maximum size are not auto-merged and route to the steward queue.
- Survivorship: when clusters merge, the oldest golden key survives; on a split, the part containing the oldest record keeps the key and the other part gets a new one.
- Merges, splits and steward reversals are recorded as status rows (active/ended, with effective timestamps); same-as links are never deleted.
- An identical MPI rerun inserts nothing; every score row carries its run ID, model version and threshold set version.

#### FR-19: Match quality measurement
Each MPI run reports, on the evaluation seed: pairwise precision, recall and F1 over all true-match pairs (not only blocked pairs); cluster-level B-cubed precision, recall and F1; the false-merge rate; and blocking recall. Results are broken down by match band and noise type.
**Consequences:** metrics are written to a table and to the CI run summary.

### 4.6 Steward Review (HITL)
**Description:** A minimal steward application shows queued pairs side by side with their context and records steward decisions. Decisions override model output on later runs and become labeled training data. Realizes UJ-2.

#### FR-20: Steward queue and decisions
A steward can list queued pairs, view the demographics and context for each pair, and record one of: match, no match, must-not-link, unmerge (split a previously merged pair out of its cluster) or defer, with a reason.
**Consequences:**
- Each decision is stored with steward identity, a timestamp and the model scores shown at decision time.
- A decided pair is not queued again unless its inputs change.
- A "no match" decision prevents the pair from auto-matching on later runs; a "must-not-link" decision creates a must-not-link constraint enforced through closure (FR-18).
- An "unmerge" decision ends the affected same-as links and splits the cluster under the FR-18 survivorship rule; nothing is deleted.
- A "defer" decision keeps the pair in the queue without changing the model output.
- If two stewards disagree on the same pair, the most recent decision wins, both stay in the audit trail, and the pair is flagged for a second review.
- Steward identity comes from the local operator identity; the steward app runs locally only and has no public deployment in the POC.

#### FR-21: Feedback retraining loop
The operator can retrain or recalibrate the MPI and ML models, using steward decisions together with ground truth.
**Consequences:**
- Each retrain records the before and after metrics from FR-19 and the training-set version.
- A retrained model is promoted only if it beats the current model on the untouched evaluation seed AND still meets the SM-C1 false-merge rate (overall F1 does not drop); otherwise the previous model stays active.
- Training sets exclude steward decisions on evaluation-seed pairs (FR-17).

### 4.7 Business Vault Derivations and Gold
**Description:** `SAT_CLAIM_COMPUTED` holds derived claim attributes: latest effective claim version, patient responsibility and adjudication flags. `LINK_VISIT_CLAIM` derives the visit-to-claim relationship. A point-in-time table over the golden person key provides snapshots over a date spine. Gold provides `DIM_PATIENT` (keyed on the golden key), `DIM_VISIT`, `DIM_PROVIDER`, `DIM_DIAGNOSIS` (ICD-10-CM), `DIM_PROCEDURE` (CPT-shaped/HCPCS/ICD-10-PCS/CDT-shaped, plus revenue code, place of service and DRG reference), `DIM_DRUG` (NDC normalized to 11-digit 5-4-2), `FCT_ELIGIBILITY_MONTHLY`, `FCT_CLAIMS_MONTHLY`, which is partitioned by claim date and clustered by golden key, and `OBT_CLAIMS_ENCOUNTERS`, which is denormalized and clustered by golden key and claim ID.

#### FR-22: Computed claim attributes
The Business Vault computes the latest effective claim version (replacements supersede, voids remove) and patient responsibility and adjudication flags from 835 adjudication data, using documented rules.
**Consequences:**
- Each computed rule has at least one dbt unit or data test with known inputs and expected outputs.
- A claim with an original, a replacement and a void contributes zero to `FCT_CLAIMS_MONTHLY`; a claim with an original and a replacement contributes once.

#### FR-23: Point-in-time access
The PIT table lets Gold join members to claims as of any date on the date spine without scanning all of satellite history.
**Consequences:** a Gold as-of query for one month reads only the matching PIT partition; its bytes processed are at most 20% of a full scan of the joined satellites on the default volume. [ASSUMPTION: 20% bound]

#### FR-24: Gold star schema and OBT
An analyst can query the Gold dimensions, the monthly claims fact and the claims–encounters OBT. Every patient-level row is keyed on the golden key.
**Consequences:**
- A patient whose records came from two payers appears as one `DIM_PATIENT` row.
- The fact and OBT tables are partitioned and clustered as described.
- `DIM_DRUG` normalizes every generated 10-digit NDC form to the correct 11-digit value (tested).

### 4.8 Consumption Surfaces
**Description:** Gold is read directly by its consumers in the POC (no de-identified layer; see §8.4). It can be consumed by a Streamlit dashboard kept in a top-level `dashboard/` folder, by ML feature extraction and by regulatory-style extracts. The same `dashboard/` folder later also holds a source-controlled Power BI project (PBIP) in Phase 2. Looker and Looker Studio are out of scope (no license).

#### FR-25: Streamlit claims dashboard
A Streamlit dashboard in the top-level `dashboard/` folder shows a claims overview built on Gold. It is deployed to GCP on Cloud Run with scale-to-zero, is reachable by authenticated invokers only (no public access), and stays within the NFR-1 budget.
**Consequences:**
- The dashboard has at least these tiles, each reading only Gold tables through BigQuery: monthly paid amount (`FCT_CLAIMS_MONTHLY`), members with active coverage (`FCT_ELIGIBILITY_MONTHLY`), top diagnoses (`DIM_DIAGNOSIS`), and cross-payer persons (`DIM_PATIENT`).
- Every dashboard query carries a bytes-billed cap (FR-34) and reads Gold directly (synthetic data only, NFR-4); the service has minimum instances set to 0, so idle cost is about $0.
- The dashboard source, its container definition and a screenshot are committed under `dashboard/`; it runs locally with the same code.
- The `dashboard/` layout leaves room for a Power BI PBIP project in Phase 2 (§8.2).

#### FR-26: Extract stubs
The operator can produce HEDIS-style measure-denominator and payer-extract stubs from Gold. They are labeled illustrative and not certified.
**Consequences:**
- Extracts read Gold directly and run on synthetic data only; identified regulatory extracts are Future Enhancement work (§8.4).
- A HEDIS-shaped denominator stub (Breast Cancer Screening style) is computed from age, sex, product line and continuous enrollment with allowable gaps as of an anchor date, using public or invented illustrative value sets (no NCQA value sets).
- A payer extract stub follows one named public layout style (MA encounter-data-like), labeled illustrative.
- Each stub writes a named file with a fixed, tested schema.

### 4.9 Orchestration and Portability
**Description:** The pipeline (generate → land → Bronze → Silver → Raw Vault → MPI → Business Vault/Gold) is declared once as a single DAG specification. A local runner executes it by default, at no cost, from the dev container and in GitHub Actions. The same specification can be rendered for a managed scheduler (Cloud Workflows with Cloud Scheduler) or as Airflow DAGs on Cloud Composer; both are behind flags that are off by default.

#### FR-27: Single DAG specification with interchangeable orchestrators
The operator can run each stage and the full pipeline from one DAG specification. The pipeline runner mints the run ID and passes it, with the period, to every task.
**Consequences:**
- The local runner is the default executor and needs no always-on service.
- The managed-scheduler and Airflow renderings are generated from the same specification, each behind its own flag (off by default); no task logic is duplicated per orchestrator.
- CI validates the DAG specification and runs the full pipeline on a small dataset with the local runner.
- Airflow-specific operators are used only inside the Airflow DAG factory, and the factory's DAGs import cleanly under the pinned Composer image when that flag is on.

#### FR-28: Idempotent, resumable runs
Rerunning any stage for the same period gives the same end state. Completed stages are skipped using persisted state markers.
**Consequences:**
- A rerun produces identical row counts and hash-key sets in every vault and Gold table, and each skipped stage is logged.
- Runs for the same client profile are serialized by a pipeline run lock that every orchestrator honors; a second concurrent run waits or exits.
- Late or out-of-order files load with their own load date and trigger a PIT and Gold rebuild for the affected periods.

### 4.10 Client Onboarding Framework
**Description:** A client profile bundles sources, mappings, environment names, thresholds and cost limits. Onboarding is documented as a guide. Realizes UJ-1.

#### FR-29: Client profile
The operator can deploy the platform for a new client profile by supplying configuration only: project, region, sources and mappings, MPI thresholds, cost limits and service flags. Each client gets its own GCP project. All platform settings are declared once in a central configuration that infrastructure, jobs, dbt, the MPI and orchestration all read.
**Consequences:**
- The repo contains two client profiles (the demo and a template), and CI validates both.
- A CI job onboards a synthetic Payer C from configuration alone (generator config, mapping, client profile entry) and passes the full pipeline on the CI volume with a zero diff outside `config/` (SM-2).

#### FR-30: Onboarding guide
A "framework for clients" guide covers adding a source, adding a schema era (including binding its schema fingerprint), tuning the MPI and turning on a managed orchestrator. A new engineer follows it to onboard a synthetic Payer C without changing any code.
**Consequences:** the guide's steps match the Payer C CI job in FR-29; a step the job does not exercise is marked as manual.

### 4.11 Coverage, Provider, Pharmacy, Cost and Privacy Requirements

#### FR-31: Eligibility and coverage vault
The Raw Vault loads coverage spans from the 834 feed into `HUB_COVERAGE`, `LINK_MEMBER_COVERAGE` and `SAT_COVERAGE` (effective and term dates, product line, plan, relationship to subscriber, maintenance type).
**Consequences:**
- Applying the generated add, change and term transactions in order reproduces the ground-truth coverage spans exactly.
- Gold exposes a continuous-enrollment check (allowable gap configurable) used by FR-26.

#### FR-32: Provider entity
Providers are loaded into `HUB_PROVIDER` keyed on NPI and linked to claims and encounters.
**Consequences:** every generated NPI passes the Luhn check; an invalid NPI is counted in the drift report and not loaded to the hub.

#### FR-33: Pharmacy claims vault
Pharmacy claims load into `HUB_PHARMACY_CLAIM`, `LINK_MEMBER_PHARMACY_CLAIM` and `SAT_PHARMACY_CLAIM`.
**Consequences:** pharmacy claim counts in the vault equal the generator's counts per source and month.

#### FR-34: Cost guardrails at every query engine
Every engine that queries BigQuery (dbt, the MPI extract, Spark BigQuery reads, BI) has a bytes-billed cap or a quota.
**Consequences:**
- The architecture lists each enforcement point; CI fails if a dbt profile or job config lacks the cap.
- Cost-bearing always-on services (Composer, scheduled Dataproc, managed scheduler) are flags that default to off; the local ML fallback (`ml_fallback_enabled`) is not cost-bearing and defaults on.
- Scratch and derived datasets may have a default table expiration; Bronze and landing never expire. A teardown target (`terraform destroy`) deletes POC datasets, Bronze Iceberg tables and their storage, landing bucket and objects (force_destroy), and Dataproc resources.
- A budget alert fires at 50%, 90% and 100% of the POC budget. This is an alert, not a hard stop.

#### FR-35: PHI log scan
CI scans logs and run summaries for the generator's name and SSN patterns.
**Consequences:** a run whose logs contain a generated SSN or a full generated name fails the scan.

### 4.12 Continuous Delivery to GCP
**Description:** The operator iterates quickly: a merge to `main` deploys the change to GCP through GitHub Actions, and a pull request shows what would change. Realizes the fast-iteration requirement.

**Primary iteration loop (decided):** during the POC build, Terraform plan/apply, dbt builds and job submissions run directly from the dev container CLI (authenticated `gcloud` + `terraform`), so changes reach GCP without waiting on CI. GitHub Actions (FR-38, FR-39) are not the inner development loop; end-to-end testing of the Actions pipeline (one green PR run and one green `main` deploy) is deferred to a late Phase 1 milestone, after the CLI-built platform works end to end. Terraform state is shared (remote GCS backend) so CLI and Actions applies never diverge.

#### FR-38: Push-to-deploy on main
A push to `main` deploys changed components to GCP through GitHub Actions: Terraform apply, dbt Fusion build, Spark job upload, and dashboard deploy (DAG upload only when the Composer flag is on).
**Consequences:**
- Only components whose paths changed are deployed; a manual dispatch can deploy all.
- Authentication uses Workload Identity Federation; no JSON keys exist (NFR-9). CLI applies impersonate the deploy service account and do not run while a `main` deploy is running.
- Deploys to the same environment are serialized by a concurrency group; a failed step stops later steps and is reported in the run summary.

#### FR-39: Pull-request plan and validate
A pull request runs validation without deploying: Terraform fmt, validate and plan, the dbt Fusion build or parse with static analysis, lint and unit tests, hashing and fingerprint golden vectors, DAG specification validation (FR-27) and a dashboard build.
**Consequences:** the Terraform plan is posted to the run summary or PR; a failing check blocks merge.

#### FR-40: Manual, skill-driven upgrades; no Dependabot
Dependabot is removed from `main` (`.github/dependabot.yml` deleted, Dependabot version updates disabled). Dependencies stay pinned (NFR-2) and are upgraded manually, on demand, through a repo-provided Claude skill that bumps pins and lockfiles and runs the version checks.
**Consequences:**
- No Dependabot pull requests or checks run on `main`.
- An upgrade is accepted only if full CI and an end-to-end regression against the last green run pass (identical Gold row counts, identical hash-key sets and MPI metrics as in NFR-2/SM-5); rollback is a revert.

## 5. Cross-Cutting NFRs
- **NFR-1 Cost:** total GCP spend from the start of the POC to its end stays under USD 5 (user-stated). Use the free tier where practical without over-optimizing for it. Managed Spark, including full-size data generation, runs on opt-in, capped Dataproc runs (FR-12). A budget alert fires at USD 5, and idle monthly spend stays at about $0. Every BigQuery query is capped by a configured maximum of bytes billed (enforcement points per FR-34). Scheduled and CI runs use local Spark and the local runner. Cost-bearing always-on services (Composer, scheduled Dataproc, managed scheduler) are off by default behind flags. Bronze Iceberg storage, any Iceberg management charges and colder-tier landing storage count against the budget; Bronze and landing are never expired, and the default 2-year, 30k-records-per-file volume must fit within the budget, otherwise the configured `volume_profile` default is lowered. Before the first full-size build, a pre-build cost estimate for the configured volume is produced and checked against the remaining budget; if the estimate or actual spend threatens the budget, scope degrades in this order: data volume first, then the number of Dataproc runs, then the deployed dashboard. At teardown, `terraform destroy` deletes landing objects and Bronze Iceberg tables and their storage, because all data is regenerable from the seeded generator (production delete lock in §8.4); Coldline/Archive early-deletion charges at teardown count as POC spend and are accepted. The Streamlit dashboard runs on Cloud Run with scale-to-zero (or an equally cheap option) and its BigQuery reads are capped. No full-size data files are committed to the repo (FR-37).
- **NFR-2 Reproducibility:** the same seed, configuration and code versions produce the same Gold row counts, hash keys and MPI metrics. Every dependency is pinned.
- **NFR-3 Auditability and lineage:** every vault and Gold row traces to a record source, a file name, an ingestion time and a run ID. MPI decisions and steward decisions are append-only.
- **NFR-4 Synthetic-only data and PHI tag metadata:** only synthetic data is processed. Every file carries the synthetic marker, CI checks it, and the loader refuses a file without it. PHI columns (name, DOB, SSN, address, MRN, member ID) carry a PHI tag in each canonical schema's configuration; in the POC the tag is metadata only, so that PHI hardening can be added later without a schema change. No PHI-shaped values appear in logs, the processing log or CI output (FR-35). The steward UI runs locally only. Keys are not used in CI (workload identity federation). Every artifact states "synthetic data, no real PHI." Masking, policy tags, restricted datasets, keyed tokens and a Safe Harbor de-identified Gold layer are Future Enhancement work (§8.4).
- **NFR-5 Data quality gates:** dbt tests (uniqueness, not-null, relationships, accepted values) block promotion to Gold when they fail. Schema-drift and cast thresholds quarantine files before Silver. Data-drift thresholds, when configured, block Gold publication; with no thresholds configured, data drift is reported and never blocks.
- **NFR-6 Portability:** no pipeline logic depends on GitHub Actions. Actions only invokes the pipeline runner or scripts. The runtime switches move between local and managed services without code changes.
- **NFR-7 dbt Fusion build:** the dbt project builds on the dbt Fusion engine, which is the only build and blocks CI. It provides column-level lineage without a dbt platform login; platform login features are optional. There is no automatic fallback to dbt Core; if Fusion cannot build the project, the outcome is reviewed by the repo owner (§8.1).
- **NFR-8 Performance (POC scale):** the full pipeline at the CI volume finishes on a free GitHub-hosted runner (about 7 GB RAM) in under 45 minutes. Default-volume runs may run locally or on Dataproc. [ASSUMPTION]
- **NFR-9 Security:** ordinary least-privilege service accounts (deploy, runtime, dashboard); per-stage service accounts are Future Enhancement work. No public buckets. Secrets only come from a secret manager or CI secrets.
- **NFR-10 Iteration speed:** a merge to `main` is deployed to GCP in under 15 minutes from push to deployed for a typical single-component change (FR-38). Measured only after the late Phase 1 Actions milestone (§4.12), over the last 3 `main` deploys. [ASSUMPTION]

## 6. Constraints and Guardrails
- **Cost:** see NFR-1. The whole POC has a total budget of less than USD 5, and a small spend is accepted. Cost-bearing always-on services (Composer, scheduled Dataproc, managed scheduler) are flags that default to off. Looker is out of scope (no license). Landing objects are tiered to Coldline and Archive and never deleted by the pipeline; POC teardown deletes them, and early-deletion charges are accepted (NFR-1). A pre-build cost estimate is required before the first full-size build, and the degrade order when the budget is threatened is volume, then Dataproc runs, then the dashboard (NFR-1).
- **Licensing:** no AMA CPT or ADA CDT descriptors or code lists, and no NCQA value sets, are committed to the repo.
- **Privacy:** real data is never allowed. CI and the loader check that every landed file has the synthetic marker. Real PHI requires the Future Enhancement PHI hardening first (§8.4).
- **Compliance:** the HIPAA-style controls are patterns only. The POC makes no compliance claim.

## 7. Non-Goals
- A production-certified X12 or FHIR implementation, or validation against real clearinghouses.
- Real-time or streaming ingestion.
- A clinical decision-support or patient-facing product.
- A live Composer or managed-scheduler deployment in the POC (both stay behind flags, off).
- A full-featured MDM product. The steward UI is minimal.
- Certified HEDIS or CMS measure calculation.

## 8. Scope and Phasing

### 8.1 Phase 1: POC (in scope)
- FR-1 to FR-29 and FR-31 to FR-40, built from the dev container CLI, run by the local pipeline runner, and deployed by GitHub Actions, within the USD 5 budget. FR-29 is pulled in from Phase 2 so that the framework claim (SM-2) is measurable in the POC.
- Phase 1 stays large on purpose (decided): there is no MVP cut. These are the most complex items, they must be built correctly, and the project needs to move fast.
- Bronze as BigLake/BigQuery Iceberg tables is in Phase 1 (decided).
- **Fusion smoke gate (early milestone, decided):** dbt Fusion is a hard requirement. Early in Phase 1, before the vault is built out, a smoke build proves that Fusion runs the in-house vault macros (hub, link, satellite) on BigQuery with strict static analysis. There is no automatic fallback to dbt Core; if the gate fails, the outcome is reviewed by the repo owner before work continues.
- Preserve the NYC Taxi POC code on a `v1` branch. Clean `main` of taxi code, datasets and GCP resources, scrapping as much as needed, and drop the Argo CD scaffolding.

### 8.2 Phase 2: Framework for Clients
- FR-30, the second client profile (its own GCP project), turning on a managed orchestrator (managed scheduler or Composer) for unattended runs, and the managed Spark runtime in the default production profile.
- Source-controlled Power BI (PBIP) dashboard in `dashboard/`, alongside the Streamlit app.

### 8.3 Out of Scope
- Real client data, Retool or a paid steward UI, a public steward UI deployment, and a paid BI tool deployment. Looker and Looker Studio are out of scope (no license).
- Iceberg for Silver, vault or Gold layers (native BigQuery only).
- Committing full-size generated data files.
- Advanced DV objects (bridges, effectivity satellites) beyond what Gold needs, deferred to v2. Exception: the effectivity satellite on the MPI same-as link (active/ended status, FR-18) is in scope for the POC.
- Readmission, FWA and cost-forecasting models. Feature tables only; the models are v2.

### 8.4 Future Enhancement Phase (not built)
Designed but not built in Phase 1 or Phase 2. The POC keeps the hooks (PHI tag metadata, a migratable config layout) so these can be added without a schema change.

| Item | What it adds | Trigger |
|---|---|---|
| PHI hardening: restricted storage | Columns tagged PHI (including `SAT_MEMBER_SENSITIVE`) routed to a restricted dataset, joined by hash key | Real PHI or a client engagement |
| PHI hardening: tokenization | Keyed HMAC person token derived from the golden person key; key held only in a secret manager | Real PHI or a client engagement |
| PHI hardening: de-identification | Safe Harbor rules (18 identifiers removed, ZIP3 with low-population 000, dates to year, ages 90+ capped) in a de-identified Gold layer that exposes no hash keys; dashboard and extracts switch to it | Real PHI or a client engagement |
| PHI hardening: access control | Column-level policy tags and masking from the PHI tag, per-stage service accounts, data-access audit logs, canary PHI checks | Real PHI or a client engagement |
| Identified regulatory extracts | Extracts on identified data | Real PHI or a client engagement |
| Production landing and Bronze delete lock | Deletion protection and a retention policy on the landing bucket and the Bronze Iceberg tables and their bucket, so `terraform destroy` cannot delete source files or the system of record | Any production deployment |
| Atmos configuration layer | Stack-based configuration over the central YAML | 3 or more clients, or multiple environments per client |

## 9. Current State and Gap (from POC findings)
- **Disposition (decided):** taxi code is sunset to a `v1` branch, and taxi datasets and resources are deleted from `main` and from GCP.
- **Reusable:** the Terraform module pattern and state backend, the CI validate and auth skeleton, TaskFlow DAG idioms with success markers, the Spark test harness, and the Makefile and devcontainer.
- **Conflicts to resolve:**
  1. Taxi naming throughout.
  2. Hadoop-catalog Iceberg Bronze and Silver, while the target is a string-only Iceberg Bronze (one table per source, feed and schema era, BigLake metastore REST catalog) and a native BigQuery Silver. The existing Iceberg Bronze work is partly reusable; the Silver Iceberg path is replaced.
  3. `composer_enabled` and `looker_enabled` are both true in the dev tfvars, which breaks NFR-1. The Looker module and the LookML content are scrapped with the taxi code (kept on `v1`).
  4. dbt is pinned to `<2.0`, which breaks NFR-7 (Fusion is the blocking build).
  5. Lifecycle goes to NEARLINE, while the target is an immutable, never-deleted landing zone tiered to Coldline at 7 days and Archive at 60 days.
  6. There are three CI workflows (`composer-sync.yml`, `release.yml`, `terraform.yml`), while the target names one; they are replaced by the FR-38 and FR-39 pipelines (taxi-specific parts move to `v1`).
  7. The Argo CD scaffolding is orphaned.
  8. `.github/dependabot.yml` runs per-commit dependency checks; it is deleted from `main`, and upgrades move to a manual repo skill (FR-40).
  9. The existing Airflow DAGs and Composer module assume Airflow as the runner; the target is a single DAG specification with a local runner, and Composer behind a flag.
  10. Terraform and provider versions are behind the target Stack: CI and the devcontainer pin Terraform 1.15.8, while the Stack pins 1.16.5. They are stepped up through the first manual upgrade (FR-40).
- **Repo layout (decided):** the target source tree is the one in the architecture spine, at the repo root, and the repo is not renamed; "GitOps Iceberg Data Platform" stays accurate because Bronze is Iceberg.
- **Net new:** FR-1 to FR-4, FR-36 and FR-37 (modular generator, data drift, sample files and README), FR-8 to FR-11 (mapping engine), FR-13 to FR-24 (vault, MPI, steward, Gold), FR-25 (Streamlit dashboard on Cloud Run), FR-27 (DAG specification, local runner and flagged renderers), FR-29 and FR-30 (client profile and guide), FR-31 to FR-35, and FR-38 to FR-40 (delivery pipeline).

## 10. Success Metrics
**Primary**
- **SM-1 MPI quality:** on the evaluation seed, pairwise F1 of at least 0.97 over all true-match pairs and at least 0.90 on edge-case true-match pairs, with cluster-level B-cubed F1 reported alongside. The false-merge rate is reported separately (SM-C1). Validates FR-16 to FR-19.
- **SM-2 Config-only onboarding:** a new source or schema era is onboarded with zero changes to code outside `config/`. Measured in Phase 1 by onboarding a synthetic Payer C through FR-8, FR-9 and FR-29; the Payer C CI job is owned by FR-29; FR-30 adds the guide in Phase 2.
- **SM-3 POC cost:** cumulative billing-export spend from the start of the POC to its end is below USD 5. Validates NFR-1 and FR-12.

**Secondary**
- **SM-4 Drift detection recall:** 100% of the injected schema drift scenarios (5 by default) are reported in the drift report, and 100% of the injected data drift scenarios are flagged. Validates FR-3, FR-11 and FR-36.
- **SM-5 Reproducibility:** two runs with the same seed give identical Gold row counts and MPI metrics. Validates NFR-2.
- **SM-6 Pipeline health:** the scheduled end-to-end CI run (local runner, local Spark, CI volume) succeeds in at least 95% of its last 20 runs. Validates FR-27 and FR-28.
- **SM-7 Steward load:** the steward queue holds at most 3% of true-match pairs on the evaluation seed. Validates FR-17.
- **SM-8 dbt Fusion build:** the Fusion build of the Raw Vault, Business Vault and Gold passes with strict static analysis on the reference dataset, with column-level lineage available. Blocking in CI and a POC exit criterion. Validates NFR-7.
- **SM-9 Repo weight:** zero full-size generated data files in the repo; each feed has exactly one 1,000-record sample file. Validates FR-37.
- **SM-10 Iteration loop:** measured after the late Phase 1 Actions milestone (§4.12), median push-to-deployed time over the last 3 `main` deploys is under 15 minutes. Validates FR-38 and NFR-10.

**Counter-metrics (do not optimize)**
- **SM-C1 False merge rate:** the share of predicted same-person record pairs (after closure) that are different true persons must stay at or below 0.5%. Counterbalances SM-1 and SM-7. Pushing auto-match rates up by merging different people (such as twins) is worse than queuing them.
- **SM-C2 Quarantine and null rate in Silver:** must not grow just to keep runs green. Counterbalances SM-6.
- **SM-C3 Synthetic realism:** do not lower the noise rate to raise SM-1. The edge-case rate must stay at 2% ± 0.5 percentage points, and the evaluation seed keeps its held-out noise scenario. Counterbalances SM-1.
- **SM-C4 Hand-written special cases:** keep the count of per-source code branches at 0. Counterbalances SM-2.

## 11. Open Questions
No product questions remain open. Resolved on 2026-10-07:
1. **Iceberg in the POC:** resolved. Bronze is BigLake/BigQuery Iceberg (1:1 copy of raw files, written by Spark) in Phase 1; Silver and all downstream layers are native BigQuery (FR-6, §8.1).
2. **Fast-path MVP cut:** resolved. Keep the full large Phase 1; no MVP cut (§8.1).
3. **Budget:** resolved. USD 5 total and at most 10 opt-in Dataproc runs are confirmed (NFR-1, FR-12).
4. **Steward UI deployment:** resolved. Local-only (FR-20, NFR-4).
5. **Repo layout and name:** resolved. Stay at the repo root (no `healthcare_data_platform/` wrapper); no rename (§9, addendum §C).
6. **Numeric targets:** resolved. SM-1, SM-6, SM-7 and SM-C1 targets are confirmed (§10).
7. **Generator sizing and repo data policy:** resolved. Modular generator, 30,000 records per file set in `volume_profile` (`.env` as a local override), 2 years of files, 5 schema drift scenarios plus data drift samples; only 1,000-record samples and a README in the repo (FR-1, FR-3, FR-36, FR-37).
8. **dbt Fusion versus Core:** resolved. Fusion is a hard requirement and the only build, proven by an early Phase 1 smoke gate; no automatic dbt Core fallback, and a failed gate is reviewed by the repo owner (NFR-7, SM-8, §8.1).
9. **Airflow as the runner:** resolved. No Airflow or Composer by default; a single DAG specification runs on a local runner, with a managed scheduler and Airflow on Composer behind flags, off (FR-27).
10. **Landing and Bronze retention:** resolved. Landing tiers to Coldline at 7 days and Archive at 60 days and is never deleted by the pipeline (POC teardown deletes it); Bronze has no expiration and is the system of record once reconciled (FR-5, FR-6).
11. **Golden key:** resolved. `HUB_PERSON` holds one golden person key for members and EMR patients, owned only by the MPI (FR-18).
12. **PHI hardening scope:** resolved. Moved to the Future Enhancement phase; the POC keeps PHI tag metadata and the synthetic-only guardrail (NFR-4, §8.4).
13. **Data drift blocking:** resolved. Reported always; blocks Gold only when thresholds are configured (FR-36, NFR-5).

**Deferred (not phase-blockers).** Each item has an owner and a condition that triggers a revisit.

| # | Item | Owner | Revisit when |
|---|---|---|---|
| D-1 | Splink backend (default: DuckDB extract and load-back; Splink 5 API to verify) | Repo owner | The default-volume MPI run exceeds the free runner's memory, or the Splink 5 API check fails |
| D-2 | Dataproc mode: resolved by the spine (Serverless runtime 3.0, standard tier, no Spot) | Repo owner | A full-size generation run exceeds its per-run cost ceiling (FR-12), or runtime 3.0 nears end of support (2027-01-31) |
| D-4 | GCP region: set per client profile (one project per client) | Repo owner | Before the first Terraform apply for the new datasets |
| D-5 | Composer image: pinned in the spine Stack; flagged off | Repo owner | When the Composer flag is turned on |
| D-6 | Bronze Iceberg catalog: resolved (BigLake metastore REST catalog; one append snapshot per delivery through a write-audit-publish branch). Early smoke test still required | Repo owner | Re-check if Iceberg charges threaten NFR-1 or the smoke test fails |
| D-7 | Exact data drift thresholds (FR-36) | Architecture workflow, then repo owner | When FR-36 profiling is implemented and first default-run profiles exist |
| D-9 | Remaining `[ASSUMPTION]` values (§12) | Repo owner | When the measurement that depends on the value first runs; confirm or adjust then |
| D-10 | When to commit the pending devcontainer changes (housekeeping, not a PRD item) | Repo owner | Before the first Phase 1 implementation PR |

Decided in this PRD and not deferred: local XGBoost for the ML fallback (FR-17), in-house vault macros with an optional package spike (FR-15), dbt Fusion as the blocking build (NFR-7) and manual skill-driven upgrades (FR-40). Remaining technical open items (managed-scheduler connector support, Iceberg bundle and catalog smoke test, Splink 5 API) are tracked in the architecture spine's Open Questions.

## 12. Assumptions Index
- §4.1: synthetic X12 is simplified and does not claim certification.
- §4.1 FR-1: the CI volume is about 5k members.
- §4.1 FR-4: the default edge-case rate is 2% ± 0.5 percentage points of true-match pairs.
- §4.3 FR-10: the default cast-failure threshold is 5% per column.
- §4.7 FR-23: a PIT as-of query reads at most 20% of the bytes of a full satellite scan.
- §5 NFR-8: the full pipeline at CI volume finishes on a free runner in under 45 minutes.
- §5 NFR-10: push-to-deployed takes under 15 minutes for a typical single-component change.

Resolved on 2026-10-07 and no longer tagged: archive tiers (now enforced, FR-5), the 7-day retention window (replaced by tiering with no pipeline deletion, FR-5) and MD5 hashing (decided, FR-13).
