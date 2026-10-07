# Requirements Catalog — Healthcare DV Platform Upgrade

Original PRD IDs are kept. Each line gives the requirement and its acceptance. Phase 1 covers everything except FR-30, which is Phase 2 (see Phasing and migration below).

## CAP-1 Synthetic healthcare data generation
- **FR-1 Deterministic population:** the generator builds persons, members with households, coverage spans, providers, P/I/D claims, 835s, pharmacy claims, and FHIR patients and encounters from a seed and `volume_profile`. Defaults are 30,000 records per file and 2 years of files. `.env` is a local override only, and config wins on conflict. Feed, source and drift components are pluggable: a new feed or scenario is added without editing the others, and size changes need no code change. Full-size default runs write directly to the landing zone. A CI volume profile exists (about 5k members). Full-size runs use opt-in Dataproc. Every output carries the synthetic marker. **Accept:** the same seed and parameters give equal SHA-256 over records sorted by the declared key.
- **FR-2 Source-shaped per era:** output covers X12-structured 834/837 (005010 X220A1, X222A1, X223A2, X224A2, X221A1, not certified), flat payer CSV, NCPDP-style CSV and FHIR NDJSON. Payer A has two claims eras with the boundary inside the window. Payer B and EMR Facility 1 have at least one era each. 837I has its own nullable sections. 834 carries INS03 021/024/001, full and change files, and plan switching with gaps. Claims have versions 1, 7 and 8. Encounters reference Patient, Practitioner and Organization, with no claim ID; the encounter-claim link exists only in ground truth. NPIs pass Luhn (prefix 80840). NDCs come in 4-4-2, 5-3-2 and 5-4-1 forms. CPT and CDT values are code-shaped only, with no AMA/ADA descriptors; ICD-10-CM/PCS and HCPCS may use public CMS files. 837I carries type of bill, admit/discharge dates, revenue codes and DRG. 835 carries allowed, paid and patient-responsibility (CAS PR) amounts and adjudication status; an adjudicated flat extract is an allowed alternative. **Accept:** sample files show each shape and era.
- **FR-3 Schema drift injection:** five default scenarios (rename, add mid-era, remove, date format change, cast failure), each pluggable. **Accept:** each injected scenario is listed in the manifest with scenario, source, file and first affected record.
- **FR-4 Identity noise and ground truth:** the full noise list per PRD §4.1 (typos, nicknames, swapped names and name-order swaps, hyphenated or compound surnames, DOB day/month swap, twins, moves, SSN missing, last-4 or default, surname changes, newborn placeholders, Jr/Sr, shared households, cross-payer switching). **Accept:** ground truth maps every member and patient record to a true person. The edge-case rate (share of true-match pairs carrying at least one edge-case noise type, configurable) is 2% ± 0.5 pp. The evaluation seed has at least one noise scenario not present in the training seed.
- **FR-36 Data drift samples:** pluggable code-mix, null-rate, unit/scale and amount-distribution shifts, listed in the manifest. **Accept:** at least one sample appears in the default run and in the committed samples. Per-file column profiles (null rate, distinct-value share, numeric mean and percentiles) flag shifts above threshold against previous files of the same source and era. Data drift is always reported, blocks Gold only when thresholds are configured, and never blocks Silver.
- **FR-37 Samples and README:** one 1,000-record sample per feed. At least one sample shows schema drift and one shows data drift. A README documents the modules, `volume_profile`, local and Dataproc runs, and sample regeneration. **Accept:** CI fails on a committed data file outside the sample folder that exceeds the sample size or size limit.

## CAP-2 Immutable landing and processing log
- **FR-5 Immutable landing:** the object path holds source, ingestion date and content hash. **Accept:** an overwrite is rejected and logged. A seen hash becomes `rejected_duplicate`; a re-delivered file with the same source name but new content lands as a new object. Objects move to Coldline at 7 days and Archive at 60 days, with no pipeline delete and no retention lock (so teardown can destroy the bucket). Every lifecycle transition and storage-class move is appended to the processing log.

## CAP-3 Bronze Iceberg raw replica
- **FR-6 Bronze replica:** one Iceberg table per (source, feed, era), written by Spark and read by BigQuery. Flat files are all STRING with original headers; nested files use one JSON string column. Columns include file name, content hash, record ordinal and ingestion timestamp. Partitioned by ingestion date. **Accept:** fingerprint selects the era (unknown means an unmapped-era table plus drift; additive-only goes to the mapped era). One snapshot per delivery is tagged with run ID and file hash, and a reload appends nothing. There are no updates, deletes or expiration. The reconcile gate checks count and per-record hash before visibility, and a failure quarantines. Bronze is prunable by ingestion date, with no coercion or renaming.
- **FR-7 EDI pre-parse:** a line-oriented derivative names its raw file and has at least one record per segment, with ISA/GS/ST control numbers, segment ID, ordinal and elements. The raw file is untouched. **Accept:** regeneration is byte-identical, checked in CI on samples.

## CAP-4 Config-driven Silver normalization, drift and quarantine
- **FR-8 Mapping registry:** canonical schemas and mappings are versioned configuration. **Accept:** the validator rejects a non-canonical target or a missing required column without a default, and runs in CI on every PR.
- **FR-9 Era-aware selection:** the mapping is chosen by source, feed and fingerprinted era, not by date. **Accept:** an unmapped era is quarantined and reported, never dropped. An additive layout uses the mapped era with drift reported. A quarantined file replays without re-landing or re-appending.
- **FR-10 Safe typing and padding:** a failed cast becomes null, the original stays in Bronze, and the failure is counted. Missing canonical columns get the mapping default. **Accept:** a cast error does not fail the run. A column whose failure rate exceeds the mapping threshold (default 5%) quarantines the whole file.
- **FR-11 Drift report:** per file, it lists unmapped columns, missing columns, cast-failure counts and the mapping version. **Accept:** every FR-3 manifest scenario appears.

## CAP-5 Interchangeable Spark runtime
- **FR-12 Runtime switch:** the same jobs run on local Spark or Dataproc Serverless through a configuration switch. **Accept:** CI and scheduled e2e use local Spark. Dataproc is opt-in, manual and capped at 10 runs (the runner refuses more), with a per-run cost ceiling. Scheduled Dataproc is flagged off. The TTL guard tears down after each run. Local Spark, Java, Python and Iceberg versions match the managed ones.

## CAP-6 Raw Data Vault
- **FR-13 Hashing and staging:** MD5, uppercase hex STRING, configured, with no FARM_FINGERPRINT. Keys are trimmed and upper-cased, with a configured delimiter and null sentinel. Keys are qualified: member `payer_id+subscriber_id+person_code`, patient `emr_system_id+MRN`, claim `payer_id+claim_id`, line `claim key+line no`, pharmacy `payer_id+Rx+fill+pharmacy NPI+DOS`. **Accept:** golden vectors pass in Spark, dbt and the MPI. The same key gives the same hub hk. The same raw ID from two payers or EMRs gives different hks.
- **FR-14 Hubs, links, satellites:** per PRD §4.4 (HUB_MEMBER, HUB_PATIENT, HUB_PROVIDER, HUB_CLAIM, HUB_CLAIM_LINE, HUB_PHARMACY_CLAIM, HUB_COVERAGE, HUB_VISIT; the listed links including LINK_VISIT_PROVIDER; the satellites including SAT_MEMBER_SENSITIVE, SAT_CLAIM_VERSION, SAT_CLAIM_ADJUDICATION and dx/proc child satellites). Native BigQuery, with load date and record source on every row. **Accept:** an identical reload adds 0 rows. A changed attribute adds exactly 1 satellite row. SSN is only in SAT_MEMBER_SENSITIVE, PHI-tagged and outside other hashdiffs. Replacements and voids share the claim hk. Late records are correct without reprocessing. Hub uniqueness and link referential-integrity tests exist.
- **FR-15 Package independence:** in-house hash, hub, link and satellite macros run on Fusion. The DV package is an optional, time-boxed spike. **Accept:** the full Raw Vault builds on the reference dataset. Any spike diffs are documented, not required to be zero.

## CAP-7 Coverage, provider and pharmacy vault
- **FR-31 Coverage:** HUB_COVERAGE, LINK_MEMBER_COVERAGE and SAT_COVERAGE (dates, product line, plan, relationship, maintenance type). **Accept:** ordered 834 transactions reproduce ground-truth spans exactly. Gold exposes a continuous-enrollment check with a configurable gap.
- **FR-32 Provider:** HUB_PROVIDER is keyed on NPI and linked to claims and encounters. **Accept:** generated NPIs pass Luhn. An invalid NPI is counted in drift and not hubbed.
- **FR-33 Pharmacy:** HUB_PHARMACY_CLAIM, LINK_MEMBER_PHARMACY_CLAIM and SAT_PHARMACY_CLAIM. **Accept:** vault counts equal generator counts per source and month.

## CAP-8 Master Patient Index
- **FR-16 Probabilistic matching:** blocked pairs from the member and patient demographics are banded by calibrated score. **Accept:** thresholds come from config and are chosen on the training seed. Blocking recall is reported. Writes are insert-only per run, and readers see only complete runs. Each pair records score, method and model version.
- **FR-17 ML fallback:** edge pairs are rescored with context; at >= 0.95 they auto-match, otherwise they go to the steward queue. **Accept:** the ML step can be switched off, and then all edges are queued. Training uses the training seed only (later plus steward decisions), split by person. Evaluation-seed data is never trained on. Ground truth is a label only. Every model version is kept and restorable. XGBoost runs locally, with no BQML.
- **FR-18 Golden key and same-as:** every member and patient record gets exactly one HUB_PERSON key. **Accept:** matching is transitive. Keys are stable unless evidence changes. Must-not-link drops edges (logged), is rechecked after closure and overrides auto bands. Oversized clusters go to the steward. Survivorship keeps the oldest key; on a split, the part with the oldest record keeps it. Merges and splits are status rows with no deletes. An identical rerun inserts nothing. Rows carry run ID, model version and threshold set version.
- **FR-19 Quality measurement:** on the evaluation seed, report pairwise P/R/F1 over all true pairs, B-cubed P/R/F1, false-merge rate and blocking recall, broken down by band and noise type. **Accept:** results are written to a table and the CI summary.

## CAP-9 Steward review and feedback retraining
- **FR-20 Queue and decisions:** list and view pairs with context. Record match, no match, must-not-link, unmerge or defer, with a reason. **Accept:** identity, time and the scores shown are stored. A decided pair is not requeued unless its inputs change. No-match blocks future auto-match. Must-not-link is enforced through closure. Unmerge ends links per survivorship. Defer keeps the pair queued. On disagreement the latest decision wins, both are audited and the pair is flagged for second review. The app is local-only and uses local OS identity.
- **FR-21 Retraining loop:** retrain or recalibrate on steward decisions plus ground truth. **Accept:** before and after metrics and the training-set version are recorded. Promotion requires beating the current model on the evaluation seed and meeting SM-C1 (F1 does not drop); otherwise the old model stays. Evaluation-seed decisions are excluded.
- **UJ-2 Steward resolves twins pair:** the 0.72 pair is marked no match with a reason, is not requeued next run and becomes a training label. **Accept:** demonstrable end-to-end, including the disagreement edge case.

## CAP-10 Business Vault derivations and Gold
- **FR-22 Computed claim attributes:** SAT_CLAIM_COMPUTED holds the latest effective version, patient responsibility and adjudication flags from the 835. LINK_VISIT_CLAIM is derived in the Business Vault. **Accept:** each rule has a dbt test. Original+replacement+void contributes 0 to FCT_CLAIMS_MONTHLY; original+replacement contributes 1.
- **FR-23 PIT:** as-of joins on the date spine over the golden key. **Accept:** a one-month as-of query reads only its PIT partition and at most 20% of the bytes of a full satellite-join scan at default volume.
- **FR-24 Gold:** DIM_PATIENT (golden key), DIM_VISIT, DIM_PROVIDER, DIM_DIAGNOSIS, DIM_PROCEDURE, DIM_DRUG, FCT_ELIGIBILITY_MONTHLY, FCT_CLAIMS_MONTHLY (partitioned by claim date, clustered by golden key), OBT_CLAIMS_ENCOUNTERS (clustered by golden key and claim ID). **Accept:** a two-payer person is one DIM_PATIENT row. Partitioning and clustering are as specified. DIM_DIAGNOSIS covers ICD-10-CM; DIM_PROCEDURE covers CPT-shaped, HCPCS, ICD-10-PCS and CDT-shaped codes plus revenue code, place of service and DRG reference. All 10-digit NDC forms map correctly to 11-digit 5-4-2 (tested).

## CAP-11 Consumption surfaces
- **FR-25 Streamlit dashboard:** in `dashboard/`, on Cloud Run with min instances 0 and authenticated invokers only. **Accept:** tiles for monthly paid, active-coverage members, top diagnoses and cross-payer persons read only Gold with a bytes cap. Source, container and screenshot are committed. It runs locally with the same code. The layout leaves room for Phase 2 PBIP.
- **FR-26 Extract stubs:** a HEDIS-style BCS denominator (age, sex, product line, continuous enrollment with gaps as of an anchor date; illustrative value sets, no NCQA) and an MA encounter-style payer extract, both labeled illustrative and synthetic-only. **Accept:** each writes a named file with a fixed, tested schema.

## CAP-12 Orchestration and portability
- **FR-27 Single DAG spec:** the runner mints the run ID and passes it, with the period, to every task. The local runner is the default. Workflows and Airflow renderings are generated from the same spec, each flagged off, and no task logic is duplicated. **Accept:** CI validates the spec and runs the full pipeline on a small dataset. Airflow operators appear only in the factory, and its DAGs import cleanly under the pinned Composer image when the flag is on.
- **FR-28 Idempotent, resumable:** completed stages are skipped using persisted state markers; late files load with their own load date. **Accept:** a rerun gives identical row counts and hash-key sets in vault and Gold, and skipped stages are logged. The run lock serializes runs per client profile; a second run waits or exits. Late files trigger a PIT and Gold rebuild for the affected periods.

## CAP-13 Client onboarding framework
- **FR-29 Client profile:** project, region, sources and mappings, MPI thresholds, cost limits and flags live in a central configuration read by infra, jobs, dbt, MPI and orchestration. Each client has its own project. **Accept:** demo and template profiles are both validated in CI. The Payer C CI job passes the full pipeline at CI volume with a zero diff outside `config/`.
- **FR-30 Onboarding guide (Phase 2):** covers adding a source, adding an era (fingerprint binding), MPI tuning and enabling an orchestrator. **Accept:** the steps match the Payer C job, and unexercised steps are marked manual.
- **UJ-1 Engineer onboards Payer C:** the validator flags unmapped and uncastable columns. A PR passes CI with a drift report. Records appear with their own record source and no model code changes. **Accept:** demonstrable, including the additive-column and unmapped-era replay edge cases.

## CAP-14 Cost guardrails and PHI-safety checks
- **FR-34 Cost guardrails:** dbt, the MPI extract, Spark BigQuery reads and BI each have a bytes cap or quota. **Accept:** CI fails when a dbt profile or job config lacks the cap. Cost-bearing services are flagged off; `ml_fallback_enabled` defaults on. Scratch datasets may expire, while Bronze and landing never do during a run. The architecture lists each enforcement point. A teardown target (`terraform destroy`) deletes the POC datasets, Bronze, landing (force_destroy) and Dataproc resources; apply and destroy are single straightforward commands. The budget alerts at 50%, 90% and 100%.
- **FR-35 PHI log scan:** **Accept:** CI fails a run whose logs or summaries contain a generated SSN or full name.

## CAP-15 Continuous delivery to GCP
- **FR-38 Push-to-deploy:** a push to main applies Terraform, builds with dbt Fusion, uploads Spark jobs and deploys the dashboard (DAGs only with the Composer flag on). **Accept:** deploys are path-filtered, with manual dispatch for all. WIF only, no JSON keys. CLI applies impersonate the deploy SA and never run during a main deploy. Deploys are serialized by a concurrency group, and a failure stops later steps. The CLI is the inner loop, and the Actions e2e milestone comes late in Phase 1.
- **FR-39 PR validate:** fmt, validate and plan; Fusion build or parse with static analysis; lint and unit tests; hash and fingerprint golden vectors; DAG spec validation; dashboard build. **Accept:** the plan is posted to the summary or PR, and a failing check blocks merge.

## CAP-16 Manual skill-driven platform upgrade
- **FR-40 No Dependabot:** `.github/dependabot.yml` is deleted. Upgrades go through a repo Claude skill that bumps pins and lockfiles. **Accept:** no Dependabot PRs. An upgrade is accepted only if full CI passes and the e2e regression matches the last green run (Gold counts, hash-key sets, MPI metrics). Rollback is a revert.

## Cross-cutting NFRs
- **NFR-1 Cost (CAP-14, CAP-5):** total spend under USD 5, with a budget alert at USD 5 and idle spend of about $0. Every BigQuery query is capped. Iceberg, management and cold-tier storage count. The default volume must fit, or `volume_profile` is lowered. A pre-build estimate is required. Degrade order: volume, then Dataproc runs, then dashboard. Teardown destroys Bronze and landing (regenerable from the seeded generator), leaving no residual storage; Coldline/Archive early-deletion charges at teardown are accepted and counted. Use the free tier where practical without over-optimizing. **Accept:** SM-3.
- **NFR-2 Reproducibility (all):** the same seed, config and versions give the same Gold counts, hash keys and MPI metrics, and all dependencies are pinned. **Accept:** SM-5.
- **NFR-3 Lineage (CAP-2, 6, 8, 9):** every vault and Gold row traces to record source, file, ingestion time and run ID. MPI and steward decisions are append-only. **Accept:** a lineage test on sampled rows.
- **NFR-4 Synthetic-only and PHI tags (CAP-1, 14):** the marker is checked by CI and the loader refuses unmarked files. PHI columns (name, DOB, SSN, address, MRN, member ID) are tagged as metadata only. No PHI-shaped values appear in logs, ops or CI. The steward UI is local. Every artifact states "synthetic data, no real PHI." **Accept:** marker check plus FR-35.
- **NFR-5 Quality gates (CAP-4, 10):** failing dbt tests block Gold. Schema and cast thresholds quarantine before Silver. Configured data-drift thresholds block Gold; with none configured, drift is reported only. **Accept:** gate tests.
- **NFR-6 Portability (CAP-12, 5):** no logic lives in Actions, and runtime switches need no code change. **Accept:** the pipeline runs via the local runner outside Actions.
- **NFR-7 dbt Fusion (CAP-6, 10):** Fusion is the only, blocking build, with login-free column-level lineage and no Core fallback. A failure is reviewed by the owner. **Accept:** SM-8 and the early smoke gate.
- **NFR-8 Performance (CAP-12):** at CI volume, the full pipeline runs under 45 minutes on a free runner (about 7 GB). Default-volume runs may run locally or on Dataproc. **Accept:** timed scheduled e2e.
- **NFR-9 Security (CAP-15):** least-privilege deploy, runtime and dashboard SAs. No public buckets. Secrets come only from a secret manager or CI secrets. **Accept:** IAM and bucket policy review in plan.
- **NFR-10 Iteration speed (CAP-15):** under 15 minutes from push to deployed, measured after the Actions milestone. **Accept:** SM-10.

## Success metrics
- **SM-1 (CAP-8):** on the evaluation seed, pairwise F1 >= 0.97 overall and >= 0.90 on edge-case pairs, with B-cubed F1 reported.
- **SM-2 (CAP-13, CAP-4):** Payer C is onboarded with zero changes outside `config/`.
- **SM-3 (CAP-14):** the billing export total is under USD 5.
- **SM-4 (CAP-1, CAP-4):** 100% of schema drift scenarios are reported and 100% of data drift scenarios are flagged.
- **SM-5 (all):** same-seed runs give identical Gold counts and MPI metrics.
- **SM-6 (CAP-12):** the scheduled e2e succeeds in at least 95% of the last 20 runs.
- **SM-7 (CAP-8, CAP-9):** the steward queue holds at most 3% of true-match pairs on the evaluation seed.
- **SM-8 (CAP-6, CAP-10):** the Fusion build of Raw Vault, Business Vault and Gold passes strict static analysis with column-level lineage. It blocks CI and is a POC exit criterion.
- **SM-9 (CAP-1):** zero full-size files in the repo and exactly one 1,000-record sample per feed.
- **SM-10 (CAP-15):** the median push-to-deployed time over the last 3 main deploys is under 15 minutes.
- **SM-C1 (CAP-8, CAP-9):** the false-merge rate after closure is at most 0.5%.
- **SM-C2 (CAP-4):** the Silver quarantine and null rates do not grow just to keep runs green.
- **SM-C3 (CAP-1):** the edge-case rate stays at 2% ± 0.5 pp, and the evaluation seed keeps its held-out noise scenario.
- **SM-C4 (CAP-13):** per-source code branches stay at 0.

## Phasing and migration
- **Phase 1 (decided, no MVP cut):** FR-1..29 and FR-31..40, built from the devcontainer CLI, run by the local runner, deployed by Actions, within USD 5. Phase 1 stays large on purpose. FR-29 is pulled in from Phase 2 so SM-2 is measurable. Bronze Iceberg and the early Fusion smoke gate are in Phase 1.
- **Phase 2:** FR-30; a second client profile in its own GCP project; a managed orchestrator (managed scheduler or Composer) for unattended runs; the managed Spark runtime in the default production profile; Power BI PBIP alongside Streamlit.
- **Disposition (decided):** preserve NYC Taxi code on a `v1` branch; clean taxi code, datasets and GCP resources from `main` and GCP; drop the Argo CD scaffolding.
- **Reusable assets:** Terraform module pattern and state backend, CI validate/auth skeleton, TaskFlow idioms with success markers, Spark test harness, Makefile and devcontainer.
- **Repo layout (decided):** the spine's source tree sits at the repo root, no wrapper folder; the repo is not renamed.
- **Current-state conflicts to resolve:** (1) taxi naming; (2) Hadoop-catalog Iceberg Bronze/Silver: Bronze partly reusable, Silver Iceberg path replaced; (3) `composer_enabled` and `looker_enabled` true in dev tfvars; Looker module and LookML scrapped (kept on `v1`); (4) dbt pinned `<2.0`; (5) lifecycle to NEARLINE vs Coldline 7d / Archive 60d; (6) three CI workflows (`composer-sync.yml`, `release.yml`, `terraform.yml`) replaced by FR-38/39; (7) orphaned Argo CD; (8) `.github/dependabot.yml` deleted, upgrades via FR-40; (9) Airflow DAGs and Composer assumed as runner vs single DAG spec plus local runner; (10) Terraform 1.15.8 stepped up to 1.16.5 through the first FR-40 upgrade.
- **Delivery (§4.12):** Terraform state is a shared remote GCS backend so CLI and Actions applies never diverge. The late Phase 1 Actions milestone is one green PR run and one green `main` deploy, after the CLI-built platform works end to end.

## Future Enhancement (designed, not built)
- **PHI hardening** (trigger: real PHI or a client engagement): restricted dataset for PHI-tagged columns (incl. `SAT_MEMBER_SENSITIVE`) joined by hash key; keyed HMAC person token from the golden key, key only in a secret manager; Safe Harbor de-identified Gold (18 identifiers removed, ZIP3 with low-population 000, dates to year, ages 90+ capped) exposing no hash keys, with dashboard and extracts switched to it; column policy tags and masking, per-stage service accounts, data-access audit logs, canary PHI checks.
- **Identified regulatory extracts** (trigger: real PHI or a client engagement).
- **Atmos configuration layer** (trigger: 3 or more clients, or multiple environments per client).
- **Landing and Bronze delete lock** (trigger: production or any non-regenerable source): deletion protection and retention on the landing bucket and Bronze tables/bucket so `terraform destroy` cannot remove them.

## Deferred decisions (owner: repo owner unless noted)
- **D-1** Splink backend, default DuckDB extract and load-back. Revisit if the default-volume MPI run exceeds free-runner memory or the Splink 5 API check fails.
- **D-2** Dataproc Serverless runtime 3.0, standard tier, no Spot. Revisit if a full-size run exceeds its cost ceiling (FR-12) or runtime 3.0 nears end of support (2027-01-31).
- **D-4** GCP region set per client profile; decide before the first Terraform apply.
- **D-5** Composer image pinned, flagged off; revisit when the Composer flag is turned on.
- **D-6** Bronze catalog: BigLake metastore REST, one append snapshot per delivery via WAP branch; early smoke test required. Revisit if Iceberg charges threaten NFR-1 or the smoke test fails.
- **D-7** Data drift thresholds (owner: architecture workflow, then repo owner); when first default-run profiles exist.
- **D-9** Remaining `[ASSUMPTION]` values; confirm when the dependent measurement first runs.
- **D-10** Commit the pending devcontainer changes before the first Phase 1 implementation PR.
