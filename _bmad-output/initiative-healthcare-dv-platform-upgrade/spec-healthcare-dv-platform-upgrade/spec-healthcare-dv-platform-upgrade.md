---
id: SPEC-healthcare-dv-platform-upgrade
companions:
  - glossary.md
  - requirements-catalog.md
  - ../architecture-healthcare-dv-platform-upgrade/architecture-healthcare-dv-platform-upgrade.md
  - ../prd-healthcare-dv-platform-upgrade/addendum.md  # adopted: tech choices and research figures
sources:
  - ../prd-healthcare-dv-platform-upgrade/prd-healthcare-dv-platform-upgrade.md
---

> **Canonical contract.** This SPEC and the files in `companions:` are the complete, preservation-validated contract for what to build, test, and validate. Source documents listed in frontmatter are for traceability — consult them only if you need narrative rationale or prose color this contract intentionally omits.

# Healthcare Data Vault Platform Upgrade

## Why

The repo owner is replacing the NYC Taxi medallion POC with an end-to-end healthcare Data Vault 2.0 platform on GCP. It must prove that DV 2.0 absorbs messy multi-payer, multi-era feeds, that dbt Fusion builds the vault as the only blocking build, and that synthetic files reach a Gold star schema with a Master Patient Index for under USD 5. Ground truth makes identity-resolution quality measured, not claimed; that is the main portfolio proof. It is also a client framework: new payers and eras onboard through configuration, and the pipeline is declared once and ports to managed orchestration. Affected: the portfolio owner, client data engineers, stewards, analysts and client buyers. No patient-facing users, no real PHI.

Terms are in `glossary.md`. FR/NFR/UJ/SM items with acceptances, plus phasing, migration and deferred decisions, are in `requirements-catalog.md`. Binding decisions are in the architecture spine.

## Capabilities

- **CAP-1 Synthetic healthcare data generation**
  - **intent:** The operator generates a seeded, modular, source-shaped synthetic population per schema era. It includes schema drift, data drift, identity noise and the ground truth.
  - **success:** The same seed and parameters give equal sorted-record SHA-256 per dataset. The generator manifest lists every injected scenario. Each feed has exactly one committed 1,000-record sample, and no full-size file is committed.
  - Governed by: AD-1, AD-3, AD-5, AD-25
- **CAP-2 Immutable landing and processing log**
  - **intent:** Every source file lands byte-for-byte under a unique content-hashed name. It tiers to colder storage, is never deleted by the pipeline (POC teardown destroys it), and its lifecycle state is always known from the processing log.
  - **success:** An overwrite attempt is rejected and logged. A re-delivered content hash is recorded as `rejected_duplicate`. Every lifecycle transition and storage-class move is appended to the log. Objects reach Coldline at 7 days and Archive at 60 days.
  - Governed by: AD-3, AD-6, AD-10
- **CAP-3 Bronze Iceberg raw replica**
  - **intent:** An analyst queries each landed file 1:1 as string rows in one Iceberg table per (source, feed, schema era). The era is identified by schema fingerprint, and each file is reconciled against landing before downstream use. EDI X12 gets a derived line-oriented form.
  - **success:** Reloading a file appends nothing. A delivery becomes visible only after the record-count and per-record-hash reconcile gate passes; a failure quarantines it. Regenerating the EDI pre-parse is byte-identical.
  - Governed by: AD-4, AD-5, AD-6, AD-22
- **CAP-4 Config-driven Silver normalization, drift and quarantine**
  - **intent:** A source or schema era is supported by mapping configuration alone. Records are safely typed into canonical entities, drift is reported, and failing files are quarantined.
  - **success:** The CI validator rejects invalid mappings. Every manifest drift scenario appears in the drift report. A quarantined file replays through Silver after a mapping fix, without re-landing it.
  - Governed by: AD-1, AD-5, AD-8, AD-9, AD-21
- **CAP-5 Interchangeable Spark runtime**
  - **intent:** The same generator and normalization jobs run on local Spark or on Dataproc Serverless, selected by a configuration switch.
  - **success:** Both runtimes give identical outputs with no code change. Dataproc runs are opt-in and the runner refuses any run past 10. The TTL guard tears capacity down after each run.
  - Governed by: AD-16, AD-21
- **CAP-6 Raw Data Vault**
  - **intent:** Silver loads into insert-only hubs, links and SCD2 satellites. All engines share one portable hashing standard, and keys are qualified by payer or EMR system.
  - **success:** An identical reload adds zero rows. The shared golden hash vectors pass in Spark, dbt and the MPI. The same raw ID from two payers produces two hub keys. A late record is absorbed without reprocessing.
  - Governed by: AD-2, AD-7, AD-11, AD-12, AD-15
- **CAP-7 Coverage, provider and pharmacy vault**
  - **intent:** Eligibility spans, NPI-keyed providers and pharmacy claims are first-class vault entities, linked to members, claims and encounters.
  - **success:** Applying the 834 transactions in order reproduces the ground-truth spans exactly. An invalid NPI is counted in drift and not loaded. Pharmacy counts equal the generator's counts per source and month.
  - Governed by: AD-8, AD-11, AD-12
- **CAP-8 Master Patient Index**
  - **intent:** Every member and EMR patient record resolves to exactly one golden person key. Must-not-link is enforced and resolution quality is measured against ground truth.
  - **success:** On the evaluation seed, SM-1 and SM-C1 hold. An identical rerun inserts nothing. Metrics are written to a table and to the CI summary.
  - Governed by: AD-2, AD-7, AD-13, AD-25
- **CAP-9 Steward review and feedback retraining**
  - **intent:** A steward decides queued pairs in a local app. Decisions override model output on later runs and feed gated retraining.
  - **success:** Every decision is stored with identity, timestamp and the scores shown. A pair decided "no match" never auto-matches again. A retrained model is promoted only if it beats the current model on the evaluation seed and meets SM-C1.
  - Governed by: AD-2, AD-13, AD-23, AD-25
- **CAP-10 Business Vault derivations and Gold**
  - **intent:** Analysts query a star schema and an OBT keyed on the golden person key. They are built from computed claim versions, derived visit-claim links and a PIT table.
  - **success:** A claim with an original, a replacement and a void contributes zero to the monthly fact. A person seen by two payers is one `DIM_PATIENT` row. A PIT as-of query reads at most 20% of a full satellite scan. The 10-to-11-digit NDC normalization is tested.
  - Governed by: AD-11, AD-12, AD-13, AD-15
- **CAP-11 Consumption surfaces**
  - **intent:** Gold is consumed directly by an authenticated, scale-to-zero dashboard and by illustrative HEDIS-style and payer extract stubs.
  - **success:** The four required tiles read only Gold under a bytes cap. Min instances is 0 and there is no public access. Each extract stub writes a file with a fixed, tested schema.
  - Governed by: AD-14, AD-16
- **CAP-12 Orchestration and portability**
  - **intent:** The pipeline is declared once and executed by a free local runner. The same declaration renders to a managed scheduler or Airflow behind flags. Runs are idempotent, resumable and serialized.
  - **success:** CI runs the full pipeline from the DAG spec. A rerun gives identical row counts and hash-key sets. A concurrent run waits or exits on the run lock.
  - Governed by: AD-10, AD-17, AD-24
- **CAP-13 Client onboarding framework**
  - **intent:** A new client is deployed from a configuration-only profile into its own GCP project, following an onboarding guide.
  - **success:** The Payer C CI job passes the full pipeline at CI volume with a zero diff outside `config/`.
  - Governed by: AD-1, AD-19
- **CAP-14 Cost guardrails and PHI-safety checks**
  - **intent:** Every BigQuery-querying engine is capped, cost-bearing services are flagged off, spend is alerted, and logs are scanned for PHI-shaped values. The log scan and caps are POC scope; AD-14's deferral covers only the PHI-hardening build.
  - **success:** CI fails when a dbt profile or job config lacks a bytes cap. The budget alert fires at 50%, 90% and 100%. CI fails a run whose logs contain a generated SSN or a full generated name.
  - Governed by: AD-14, AD-16
- **CAP-15 Continuous delivery to GCP**
  - **intent:** A PR validates and plans without deploying, and a push to `main` deploys only the changed components through WIF. The CLI remains the inner loop.
  - **success:** A failing check blocks merge. Deploys are path-filtered and serialized per environment. No JSON keys exist.
  - Governed by: AD-18, AD-19 (per-client project targets), AD-20
- **CAP-16 Manual skill-driven platform upgrade**
  - **intent:** Pinned dependencies are upgraded on demand through a repo Claude skill, and Dependabot is removed.
  - **success:** An upgrade is accepted only if full CI passes and the end-to-end regression is identical to the last green run. Rollback is a revert.
  - Governed by: AD-20

## Constraints

- Total GCP spend for the POC stays under USD 5 (NFR-1). The budget alert only alerts; it does not stop spend. A cost estimate is required before the first full-size build. If the budget is threatened, scope degrades in this order: volume, then Dataproc runs, then the dashboard.
- Only synthetic data is allowed. The loader and CI refuse files without the synthetic marker. PHI tags are metadata only in the POC.
- Reproducibility: the same seed, configuration and versions give the same Gold counts, hash keys and MPI metrics. Every dependency is pinned.
- Lineage: every vault and Gold row traces to a record source, file name, ingestion time and run ID. MPI and steward decisions are append-only.
- dbt Fusion is a hard requirement and the only blocking build, with no automatic dbt Core fallback. An early Phase 1 Fusion smoke gate (in-house macros on BigQuery, strict static analysis) must pass, and a failure is reviewed by the repo owner before work continues.
- Cost-bearing always-on services (Composer, scheduled Dataproc, managed scheduler) are flagged off by default. Dataproc is opt-in, with at most 10 runs.
- GCP only, with one project per client. Bronze is the only Iceberg layer; Silver and everything downstream are native BigQuery.
- During a run, landing objects are never deleted by the pipeline (lifecycle tiering only) and Bronze never expires. At POC teardown `terraform destroy` deletes landing (force_destroy, no retention lock) and Bronze, since the seeded generator regenerates all data; Coldline/Archive early-deletion charges are accepted.
- No pipeline logic depends on GitHub Actions. Authentication uses WIF only, with no JSON keys.
- No AMA CPT or ADA CDT descriptors or code lists and no NCQA value sets are committed. The POC makes no compliance claim.

## Non-goals

- Production-certified X12 or FHIR, or validation against real clearinghouses.
- Real-time or streaming ingestion.
- Clinical decision support or any patient-facing product.
- A live Composer or managed-scheduler deployment in the POC.
- A full-featured MDM product, Retool or a paid steward UI, or a public steward UI.
- Certified HEDIS or CMS measure calculation.
- Looker, Looker Studio or any paid BI deployment. Power BI PBIP is Phase 2.
- Iceberg for Silver, vault or Gold.
- Committing full-size generated data.
- Advanced DV objects beyond Gold's needs (bridges, effectivity satellites). The exception is the effectivity satellite on the MPI same-as link, which is in scope.
- Readmission, FWA and cost-forecasting models (v2; feature tables only).
- **Future Enhancement phase (designed, not built):** PHI hardening (restricted storage, HMAC tokenization, a Safe Harbor de-identified Gold, policy tags and access control), identified regulatory extracts, the Atmos configuration layer, and a production delete lock (deletion protection and retention) on the landing bucket and Bronze tables and bucket.

## Success signal

- **SM-1 / SM-C1 / SM-7:** an MPI evaluation-seed test asserts pairwise F1 >= 0.97 overall and >= 0.90 on edge cases, a false-merge rate <= 0.5%, and a steward queue <= 3% of true-match pairs.
- **SM-2 / SM-C4:** the Payer C CI job is green with `git diff --stat` empty outside `config/` and zero per-source code branches.
- **SM-3:** the cumulative billing export is below USD 5 at POC end.
- **SM-4:** the drift report contains 100% of the manifest's schema drift scenarios and flags 100% of its data drift scenarios.
- **SM-5:** two runs with the same seed give identical Gold row counts and MPI metrics.
- **SM-6:** the scheduled e2e run succeeds in at least 95% of its last 20 runs.
- **SM-8:** the Fusion build passes with strict static analysis and column-level lineage, and it blocks in CI.
- **SM-9:** the repo-weight CI guard passes.
- **SM-10:** the median push-to-deploy time over the last 3 `main` deploys is under 15 minutes.
- **SM-C2 / SM-C3:** guarded counter-metrics. The Silver quarantine and null rates must not grow to keep runs green, and the edge-case rate stays at 2% ± 0.5 pp.

## Assumptions

- PRD `[ASSUMPTION]` values: CI volume ~5k members; edge-case rate 2% ± 0.5 pp; cast-failure threshold 5% per column; PIT bound 20%; CI pipeline < 45 min on a free runner; push-to-deploy < 15 min; X12 simplified, not certified. Revisited when the dependent measurement first runs (D-9).
- Where the addendum and the spine differ, the spine wins.
- FR-30 is Phase 2 but lives in CAP-13 for a capability home.

## Open Questions

- Does Cloud Workflows support waiting on Dataproc batches and Cloud Run jobs? (unverified, spine)
- Does the BigLake REST catalog's 1,000-tables-per-bucket scope apply here? (unverified, spine)
- Is `iceberg-gcp-bundle` required alongside iceberg-spark-runtime 1.12.0 on Dataproc runtime 3.0? (unverified, spine)
- Splink 5.0.0: what are the API changes from v4, and is DuckDB the right backend? (unverified, spine; D-1)
- Does the BigLake REST catalog work on runtime 3.0 with Iceberg 1.12.0? It is confirmed only for 2.3.10+, so an early smoke test (create, append, read from BigQuery) is required. (spine; D-6)
- What are the exact data drift thresholds (D-7)? They are pending the first default-run profiles.
