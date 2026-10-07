---
title: Reconcile — PRD addendum + PRD reviews vs architecture spine
date: 2026-10-07
inputs: [addendum.md, review-adversarial.md, review-healthcare-domain.md, review-rubric.md]
spine: architecture-healthcare-dv-platform-upgrade.md (memlog authority applied)
---

# Reconcile: addendum and reviews vs spine

Most review findings were absorbed by the PRD revision (half-open bands, MD5/in-house macros, payer-qualified keys, coverage/pharmacy/provider/835 entities, local XGBoost, SM-8, CI volume, capped Dataproc). The gaps below are what did not reach the spine.

## A. Upstream PRD update needed (deliberate user overrides — not spine defects)

| # | PRD / addendum says | Spine (memlog) | Action |
|---|---|---|---|
| U1 | NFR-7 / addendum D: dbt Core blocking, Fusion non-blocking; SM-8 "non-blocking in CI" | AD-15 Fusion blocking, Core local fallback | Update NFR-7, SM-8, addendum D dbt row, `require-dbt-version` |
| U2 | FR-5 / addendum D "Archive tier: policy documented only"; 7-day delete | AD-3 Standard->Coldline 7d->Archive 60d, never deleted | Update FR-5, NFR-1 idle-cost wording, addendum D/F (NEARLINE replacement) |
| U3 | Addendum D orchestration: Airflow 3.x DAGs, `airflow standalone`, Cosmos/BashOperator; SM-6 assumes scheduled runs | AD-17 local runner default, Workflows/Composer flagged off | Update FR-27, addendum D, SM-6 (who schedules — see B7) |
| U4 | Addendum D Dataproc "2.x / Spot"; memlog note Py3.11 | AD-21 Dataproc Serverless 3.0, Py3.12 | Update addendum D; note 3.0 is non-LTS (EOL 2027-01-31) |
| U5 | Addendum F/C: Bronze per file ("1:1 raw replica"), partitioned by ingest date; datasets `bronze_raw`, `silver_staging`, `mpi_steward`; folders `ingestion_pyspark/`, `identity_splink_ml/`, `dbt_bigquery_project/` | AD-4 per (source, feed, era) with `_raw_line` reconcile; datasets `silver`, `steward`, namespaces `bronze_<source>`; dirs `ingestion/`, `mpi/`, `dbt/` | Update addendum F/C names |
| U6 | NFR-1: "Bronze has a default table expiration outside the landing zone" | AD-3/AD-4: Bronze is the system of record, never updated | Contradiction created by override U2; remove Bronze expiration from NFR-1 (or spine must say which wins) |
| U7 | Addendum A/diagram: Looker/Tableau BI, BQML option, FARM_FINGERPRINT, `LINK_MEMBER_SAME_AS`/`MASTER_MEMBER_HK`, `PIT_MEMBER_CLAIMS`, `DIM_PATIENTS` | HUB_PERSON / `golden_person_hk`, `PIT_PERSON_CLAIMS`, `DIM_PATIENT` | Glossary "Golden key = MASTER_MEMBER_HK" (rubric) must change to `golden_person_hk` |

## B. Requirements / capabilities with no home in the spine

| # | Source | Gap | Suggested home |
|---|---|---|---|
| B1 | Domain F5, PRD NFR-4 | Safe Harbor rules (ZIP3/000, year-only dates, age 90+) not stated; BigQuery policy tags + dynamic masking absent; `SAT_MEMBER_SENSITIVE` (SSN out of hashdiff) missing from AD-14 and ER diagram | Extend AD-14; add SAT_*_SENSITIVE to ER in `restricted_phi` |
| B2 | Adversarial M3, rubric | Steward reversal / un-merge / golden-key split representation under "links never deleted"; split survivorship (which key is reissued); two-steward disagreement = latest wins + second-review flag | AD-13: status/effectivity sat on same-as link (e.g. `SAT_SAME_AS_STATUS`) |
| B3 | Adversarial C1 | Transitive-closure conflict rule (max cluster size, must-not-link blocks closure) — must-not-link named but not that it blocks closure | AD-13 |
| B4 | Adversarial C1, rubric FR-21 | MPI evaluation harness: score type (probability vs weight) + calibration, held-out noise seed, pairwise + B-cubed metrics with denominators, train/test split by true person, ML bootstrap labels; retrain promotion gate (F1 no drop, SM-C1 holds) | New AD or mpi/ section; where ground truth is stored and fenced off from features |
| B5 | Adversarial M3 | MPI partial load-back atomicity: insert-only per `run_id` lacks a run-complete marker so dbt may read a half-written run | AD-13: dbt reads only `run_id`s marked complete in `ops.run_events` |
| B6 | Adversarial M3 | Concurrent pipeline runs racing `ops` state; AD-18 only covers Terraform state lock | AD-17: single-run lock / concurrency group |
| B7 | PRD SM-6, NFR-8 | Scheduled E2E CI run at "CI volume" has no home: workflows are only `pr-validate.yml`, `deploy-main.yml`; no CI-volume profile in config | Add scheduled GitHub Actions workflow + `volume_profile` in config |
| B8 | Domain F2/F4, PRD FR-24 | Claim header vs line grain (`SAT_CLAIM_HEADER`, line key / multi-active sat), 835 adjudication vault object (remittance canonical exists, no sat/link), `DIM_DIAGNOSIS`/`DIM_PROCEDURE` split, `FCT_CLAIMS_MONTHLY` latest-version rule | ER diagram + Gold conventions |
| B9 | Domain F1 | `person_code` (subscriber+dependent) not in member business key; AD-7 says only "payer-qualified" | AD-7 / hashing.yaml |
| B10 | Domain F4 | Licensing constraint (no CPT/CDT descriptors in a public repo), NDC 10->11 normalization, NPI Luhn | Quiet constraint: add to datagen + Silver mapping rules |
| B11 | Domain F6 | Encounter must not carry claim_id; LINK_VISIT_CLAIM matched on patient+DOS+NPI+facility; ground truth emitted separately | AD-12 derivation rule |
| B12 | Domain F3, PRD FR-25/26 | HEDIS continuous-enrollment stub and regulatory extract stubs: capability map puts FR-26 under `dashboard/` only; no extract unit/location | Capability map row; `gold_deid` extracts dir |
| B13 | Addendum D | X12 EDI pre-parse to JSONL — no unit owns parsing (datagen vs ingestion) | AD-4/AD-5 or ingestion/ |
| B14 | Adversarial L1, PRD FR-1 | Reproducibility: seed + content-hash of sorted records not stated | datagen convention |
| B15 | Adversarial H2, addendum E | Teardown target, BigQuery time-travel window, per-layer storage budget absent; Makefile lists no `teardown` | AD-16 |
| B16 | Addendum D/E | Region (us-central1 vs us-east1; free 5 GB GCS only in US regions) not decided | Conventions / client yaml |
| B17 | Adversarial H1 | Landing immutability mechanism unstated (unlocked retention policy vs precondition `ifGenerationMatch=0`); "never lock" constraint missing; Coldline 90d / Archive 365d minimum-storage charges on teardown | AD-3 |
| B18 | Memlog (AD-14 implication) | PHI leaves BigQuery: Splink/DuckDB Parquet extracts and XGBoost training on dev container disk — no rule for local PHI handling/cleanup | AD-14 |

## C. Contradictions / spine-internal issues

| # | Issue |
|---|---|
| C1 | Memlog decision: Fusion "with dbt platform login features (lineage, CLL)" is a HARD requirement; spine Deferred table defers platform-login features. No memlog entry supersedes it — needs user confirmation or memlog entry. |
| C2 | AD-16 "Spot where available" — Spot does not apply to Dataproc Serverless standard tier (adversarial H2); with Serverless 3.0 chosen, Spot is effectively unavailable. Cost math must not assume it. |
| C3 | Stack lists astronomer-cosmos; PRD NFR-7 says Fusion track uses BashOperator, not Cosmos (Cosmos/Fusion manifest compatibility untested). |
| C4 | AD-1 "everything in config/" vs addendum `.env` `RECORDS_PER_FILE=30000` / file span — sizing source of truth unclear. |
| C5 | Memlog: reconcile gate "before Coldline"; AD-3 lifecycle is age-based only, so an unreconciled/quarantined file still tiers to Coldline/Archive at 7/60 days (retrieval cost on rerun). |
| C6 | Memlog assumption (lineage columns, hash spec, era authority, `_raw_line`) "accepted by silence — confirm at review" is marked ADOPTED in spine without a confirmation entry. |
| C7 | Rubric: USD 5 / SM targets — PRD now confirms them; no conflict. Spine cost story OK but has no explicit Dataproc per-run cost cap (only "at most 10 per POC"). |
