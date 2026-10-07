---
title: Healthcare Data Vault Platform Upgrade — PRD Addendum
status: draft
created: 2026-10-07
updated: 2026-10-07
---

# Addendum: Implementation Context

This addendum holds the implementation material that does not belong in the PRD: technology choices, layout, diagram, trade-offs and research figures. It was input for the architecture workflow. The final architecture spine (`_bmad-output/initiative-healthcare-dv-platform-upgrade/architecture-healthcare-dv-platform-upgrade/architecture-healthcare-dv-platform-upgrade.md`) now binds the technology choices; where this addendum and the spine differ, the spine wins.

## A. Target Architecture (as stated by the user, verbatim)

Bronze: payer feeds (ANSI 834 eligibility, 837P/I/D + pharmacy claims) and EMR HL7 FHIR (visits/diagnoses/procedures), 2022-present -> GCS immutable landing (compressed CSV/JSON/EDI) -> GCS Coldline/Archive 1:1 retention; BigQuery external/Iceberg tables, 1:1 raw replica, all STRING/VARIANT, preserves headers & drift, partitioned by _FILE_NAME & _INGESTED_AT. Silver staging: config-driven PySpark schema engine (Serverless Spark/Dataproc) reading versioned YAML/JSON mappings per payer & era (Payer A 2022-2023, Payer A 2024-present, Payer B, EMR), column standardization (MBR_NO->member_id), TRY_CAST typification, drift resolution & default padding -> BigQuery Silver normalized canonical staging. Raw Data Vault (native BigQuery dbt + AutomateDV): stage models generate hash keys (MD5/SHA256/FARM_FINGERPRINT), HASHDIFF, LOAD_DATE, RECORD_SOURCE; HUB_MEMBER, HUB_CLAIM, HUB_VISIT; LINK_MEMBER_CLAIM, LINK_VISIT_CLAIM; SAT_MEMBER_DEMOGRAPHICS (name, DOB, SSN, gender, address), SAT_CLAIM_LINES (dx, billed/paid, status) SCD2. Business Vault: Splink Fellegi-Sunter MPI on demographics; >=90% auto-match, <50% new golden key, 50-89% (~2% edge cases: typos, twins, address inversions) -> ML fallback (XGBoost/BQ ML using claims history, visit proximity, provider patterns); ML>=95% auto-match else HITL steward queue UI (Retool/custom) with feedback retraining loop; LINK_MEMBER_SAME_AS (LINK_SAME_AS_HK, MASTER_MEMBER_HK golden key, TARGET_MEMBER_HK), SAT_MPI_MATCH_DETAILS (score, method, status), SAT_CLAIM_COMPUTED (patient responsibility, adjudication flags), PIT_MEMBER_CLAIMS (date spine). Gold: star schema DIM_PATIENTS (via golden key), DIM_VISITS, DIM_DIAGNOSES (ICD-10/CPT), FCT_CLAIMS_MONTHLY (partition claim date, cluster member key, via PIT, + SAT_CLAIM_COMPUTED); OBT_CLAIMS_ENCOUNTERS denormalized/materialized view clustered by master_member_hk & claim_id. Consumption: BI (Looker, PowerBI, Tableau), predictive ML (readmission, FWA, cost forecasting), regulatory exports (HEDIS, CMS, payer extracts).

**Decision note (2026-10-07):** "external/Iceberg" Bronze resolves to Iceberg. Bronze is a 1:1 copy of the raw files in Iceberg tables written by Spark, one table per (source, feed, schema era), cataloged in the BigLake metastore REST catalog (D-6 resolved), with one append snapshot per delivery through a write-audit-publish branch and a reconcile gate. The "GCS Coldline/Archive 1:1 retention" in §A is now enforced: landing objects move to Coldline at 7 days and Archive at 60 days and are never deleted. Silver normalized and everything downstream (Raw Vault, Business Vault, Gold) are native BigQuery tables, because dbt Fusion has no native Iceberg support (only through DuckDB, which does not suit a Spark-written lake). Iceberg stays where it adds value (open format, schema evolution, raw-data snapshots) and stays out of the dbt layers.

**Corrections to §A (from review, applied in the spine):** BigQuery has no VARIANT type (use JSON or a JSON string column). `_FILE_NAME` is a pseudo-column and cannot be a partition key; store the file name as a column and partition Bronze Iceberg tables by ingestion date. Member keys must be payer-qualified, claims need header and line grain plus 835 adjudication, and `DIM_DIAGNOSES` is split into diagnosis and procedure dimensions (see PRD FR-13, FR-22, FR-31 to FR-33). FARM_FINGERPRINT is excluded for portability. The golden key is `HUB_PERSON.golden_person_hk` (members and EMR patients), not `MASTER_MEMBER_HK`, and `LINK_VISIT_CLAIM` is a Business Vault derivation. BI is a Streamlit dashboard in `dashboard/` (Power BI PBIP in Phase 2); Looker and Tableau are out of scope.

## B. Architecture Diagrams

Superseded: the earlier diagram predated the architecture decisions. The authoritative diagrams (container view, data process flow, file lifecycle states, developer and maintenance flows, orchestration, vault entities, deployment) are in the architecture spine's **Structural Seed** section: `_bmad-output/initiative-healthcare-dv-platform-upgrade/architecture-healthcare-dv-platform-upgrade/architecture-healthcare-dv-platform-upgrade.md`. They are not duplicated here.

## C. Target Repo Layout

Superseded: the user's original layout (a `healthcare_data_platform/` wrapper, `ingestion_pyspark/`, `identity_splink_ml/`, `dbt_bigquery_project/`) is replaced by the source tree in the architecture spine's Structural Seed (repo root: `config/`, `datagen/`, `ingestion/`, `dbt/`, `mpi/`, `extracts/`, `steward_ui/`, `dashboard/`, `pipeline/`, `dags/`, `infra/`, `versions.yaml`, `.claude/skills/platform-upgrade/`, `.github/workflows/`, `Makefile`). The repo keeps its name. See the spine for the full tree; it is not duplicated here.

## D. Technology Choices and Trade-offs (as bound by the spine)

Versions follow the architecture spine's Stack table; all are pinned, with non-registry pins in `versions.yaml`.

| Concern | POC default | Production / client option | Trade-off |
|---|---|---|---|
| Language | Python 3.12 everywhere (uv projects pin `==3.12.*`); uv 0.12.23, ruff 0.16.10, pytest 9.1.1 | Same | The flagged-off Composer image is exempt |
| Spark runtime | Local PySpark matching Dataproc Serverless runtime 3.0 (Spark 4.0, Java 21) for CI and scheduled runs; Dataproc Serverless 3.0, standard tier, opt-in, at most 10 runs, TTL per batch, for full-size generation | Same, sized for the client | Runtime 3.0 is non-LTS (end of support 2027-01-31); Spot does not apply to Serverless standard tier; a daily Dataproc schedule would exceed the budget, so it is flagged off |
| Bronze tables | Iceberg (iceberg-spark-runtime-4.0_2.13 1.12.0), one table per (source, feed, schema era), BigLake metastore REST catalog (D-6 resolved), STRING columns, partitioned by `day(_ingested_at)`, write-audit-publish + reconcile gate, never expired | Same | Iceberg management fee is $0.12/DCU-hr; metastore operations free up to about 5k Class A and 50k Class B [S]. REST catalog on runtime 3.0 needs an early smoke test |
| BigQuery connector | spark-bigquery-connector 0.42.3 (bundled with runtime 3.0) | Same | Deliberately the bundled version |
| Silver and downstream storage | Native BigQuery tables (decided): 8 canonical Silver entities, Raw Vault, Business Vault, Gold | Same | dbt Fusion has no native Iceberg support, so Iceberg stops at Bronze |
| Synthetic data size | config `volume_profile` (`RECORDS_PER_FILE=30000`; `.env` local override only), 2 years of files, 5 schema drift scenarios plus data drift samples; generated on opt-in Dataproc; only 1,000-record samples and a README in the repo | Sized per client | Keeps the repo light; full volume must stay within the USD 5 budget |
| Landing lifecycle | Standard -> Coldline at 7 days -> Archive at 60 days, never deleted; content-hashed names, overwrite rejected, no retention lock | Same, with a locked retention policy if required | Minimum storage is 90 days for Coldline and 365 days for Archive [K]; early deletion at teardown is charged |
| EDI X12 | Pre-parse to JSONL; raw copy kept in landing | Same, or a commercial parser | X12 does not map to CSV |
| dbt | dbt Fusion 2.0.6, the only blocking build, `static_analysis: strict`, login-free column-level lineage; no automatic dbt Core fallback; early Phase 1 Fusion smoke gate (in-house macros on BigQuery, strict static analysis), failure reviewed by the repo owner | Same; dbt platform login optional | No Python models under Fusion |
| DV package | In-house `dv_hash` / `build_hub` / `build_link` / `build_sat` macros (primary); AutomateDV as an optional spike | datavault4dbt | datavault4dbt has a Fusion warning on BigQuery `stage` [S] |
| MPI engine | Splink 5.0.0 with DuckDB 1.5.6 (in-memory): extract, score, load back to BigQuery | Splink on the Spark backend at scale | Splink 5 API changes unverified (spine open question) |
| ML fallback | Local XGBoost 3.4.1 (decided), behind `ml_fallback_enabled` | BigQuery ML boosted trees | BQML costs about $312.50/TB for model creation [K] |
| Steward UI | Streamlit 1.65.0, local only (decided) | Retool or a custom app | Local OS identity is the steward identity |
| BI | Streamlit 1.65.0 dashboard in `dashboard/` on Cloud Run, min instances 0, bytes-billed cap, reads `gold` directly | Power BI (PBIP) in Phase 2 | Looker is out (no license; flag off) |
| Orchestration | `pipeline/dag_spec.py` declared once; local Python runner (default, $0); Cloud Workflows + Scheduler (`workflows_enabled`) and Airflow 3 factory on Composer (`composer_enabled`, image composer-3-airflow-3.3.1-build.2) both off; BashOperator over Cosmos (astronomer-cosmos 1.15.1 when flagged) | Workflows or Composer turned on | Composer costs about $300–450/month [K] |
| Central config | Plain YAML in `config/` + JSON Schema, read by Terraform `yamldecode` and a shared Python loader | Atmos (Future Enhancement phase) | Atmos deferred until 3+ clients or multi-env |
| Infrastructure | Terraform 1.16.5, hashicorp/google and google-beta 8.6.0, tflint 0.64.0; one GCP project per client; state bucket unversioned (POC) | Versioned state bucket | Provider stepped 5 -> 8.6.0 with a plan review at each step |
| Delivery pipeline | CLI-first (impersonate deploy SA); GitHub Actions `pr-validate.yml`, `deploy-main.yml`, `scheduled-e2e.yml` via WIF; no Dependabot; manual upgrades via `.claude/skills/platform-upgrade/` and `make upgrade` | Same, with environment approvals | Speed over gating; target under 15 minutes push-to-deployed [ASSUMPTION] |
| PHI handling | PHI tag metadata only + synthetic-only guardrail | Restricted dataset, HMAC tokens, Safe Harbor `gold_deid`, policy tags (Future Enhancement phase) | Not built in the POC |
| Region | Set per client profile | Client choice | The GCS free 5 GB applies only to us-east1, us-west1 and us-central1 |
| Synthetic source | Pure PySpark and Faker; Synthea optional | Synthea for clinical depth | Synthea needs Java; keep it out of CI |

## E. Research Figures (confidence-tagged; verify before publishing)

- **BigQuery free tier [K]:** 1 TiB of queries and 10 GiB of storage per month. The Sandbox is unsuitable (60-day table expiry, DML limits).
- **GCS free tier [K]:** 5 GB-month of Standard storage, in US regions only. New accounts get a $300 credit for 90 days.
- **Default synthetic volume:** 30,000 records per file across 2 years of files per feed (set in config `volume_profile`; `.env` overrides locally only); full-size files are generated on Dataproc, and only 1,000-record samples are committed.
- **Guardrails:** `maximum_bytes_billed` set in profiles and every other BigQuery client, a $5 budget alert (alert only, not a stop), expensive services flagged off, a teardown target, and partitioning and clustering on large tables.
- **Unverified:** the BQML figures and the Composer per-DCU snippet are garbled or unverified ([S]/[K]); confirm them on cloud.google.com before quoting them in the README.

## F. Current Repo Reuse Map (from POC findings)

- **Keep:**
  - `infra/` structure and the state backend
  - the composer module, behind `composer_enabled` (default `false`)
  - CI job skeletons and GCP authentication
  - Makefile and devcontainer
  - TaskFlow DAG idioms and success markers
  - the Spark pytest harness
- **Replace:**
  - all taxi Spark logic (`TRIP_COLUMNS`)
  - the dbt `nyc_taxi_gold` models and the seed
  - the LookML content and the `infra/modules/looker` module (scrapped; kept on `v1`)
  - the `composer-sync.yml`, `release.yml` and `terraform.yml` workflows (by FR-38/FR-39 pipelines)
  - the Hadoop-catalog Iceberg path (Bronze moves to BigLake/BigQuery Iceberg; Silver becomes native BigQuery) and the BigLake Silver registration
  - the NEARLINE lifecycle rule (by Coldline at 7 days, Archive at 60 days, no delete)
  - the existing Airflow DAGs as the runner (by `pipeline/dag_spec.py` and the local runner)
- **Add in Terraform:**
  - landing bucket with content-hashed object names, overwrite rejected, Coldline/Archive tiering, no delete rule
  - BigLake metastore REST catalog and Iceberg warehouse bucket; datasets per the spine conventions (`silver`, `raw_vault`, `business_vault`, `gold`, `ops`, `steward`, `mpi_eval`)
  - (Future Enhancement only) `restricted_phi` dataset, policy tags taxonomy and data masking
- **Drop:** `gitops/` (Argo CD scaffolding) and `.github/dependabot.yml`.
