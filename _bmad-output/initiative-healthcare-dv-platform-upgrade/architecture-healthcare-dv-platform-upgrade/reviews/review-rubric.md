# Rubric Review — Architecture Spine (Healthcare DV Platform Upgrade)

Date: 2026-10-07. Inputs: spine, .memlog.md (later supersedes earlier), PRD, brownfield repo.

## Verdict

Strong spine. 21 ADs cover the real cross-unit divergence points (contract, writer ownership, hash spec, lineage, era identity, Silver shape, quarantine precedence, MPI ownership, PHI boundary, orchestration spec, deploy/auth, versions). Rules are mostly concrete and enforceable. Gaps: the PHI boundary leaves de-identification rules and column security undecided, brownfield migration is unaddressed, and the operational envelope has no observability/alerting or local Spark parity decision. A few naming inconsistencies. Pass with fixes.

## Checklist

| Criterion | Result |
| --- | --- |
| Fixes divergence points, misses none | Mostly; gaps G1, G2, G4 |
| Rules enforceable and preventive | Mostly; AD-14 and AD-18 partly prose-only |
| Deferred cannot cause divergence | Pass (drift thresholds come from config; Atmos layout constrained) |
| Tech verified-current | Pass per memlog sweep wf_5ff86a46-f83; open items listed as Open Questions |
| Ratifies brownfield repo | Partial; G3 |
| Covers PRD capabilities | Pass via binds and capability map; NFR-4 detail gap |
| Operational envelope decided/deferred/open | Partial; G4, G5 |

## Findings

**G1 (high) — AD-14 omits policy tags + dynamic masking and Safe Harbor rules.** NFR-4 requires BigQuery policy tags with dynamic data masking on PHI columns and Safe Harbor transforms (ZIP3 with 000 low-population, year-only dates, age 90+ cap). The spine says only "restricted_phi dataset + HMAC token." dbt `gold_deid` and the dashboard could each implement de-identification differently. Fix: add to AD-14 that policy tags come from config PHI tags via Terraform, and that Safe Harbor transforms are one macro set driven by `config/standards/deid.yaml`. Alternatively, record a user decision that dataset isolation replaces policy tags (upstream PRD update).

**G2 (medium) — Local vs Dataproc Spark parity undecided.** CI/local runs use local Spark (NFR-8, FR-12), while Dataproc is 3.0 (Spark 4.0, Java 21, Iceberg 4.0_2.13). Nothing pins the local PySpark/Java/Iceberg jars to match. Fix: add a rule that local Spark versions come from `versions.yaml` and match the Dataproc runtime.

**G3 (medium) — Brownfield migration not ratified.** The repo has `src/{composer,dbt_project,looker_project,spark_jobs}`, `gitops/`, workflows `terraform.yml`/`composer-sync.yml`/`release.yml`, and providers pinned `~> 5.0` with `required_version >= 1.5`. The spine's tree (root `dbt/`, `ingestion/`, `pr-validate.yml`, `deploy-main.yml`, provider 8.6.0) silently replaces these. Fix: add a migration note: taxi code retired to `v1` tag, `src/` and `gitops/` removed or mapped, workflows renamed, provider stepped 5 -> 6 -> 7 -> 8 (memlog), Looker/Composer modules kept flagged.

**G4 (medium) — Operations: no monitoring/alerting/failure-notification decision.** Budget alerts and `ops.run_events` exist, but no AD covers how a failed run, quarantine, or stuck file surfaces (log-based alert, CLI report, none). With the Workflows flag on, unattended failures would be invisible. Fix: decide, or list under Deferred with the trigger "workflows_enabled = true".

**G5 (low) — Environments.** Only dev = demo client. No statement that there is no staging/prod for the POC, or how PR plan runs against which project. Fix: one line in AD-19 or Deferred.

**G6 (low) — Naming inconsistency for unmapped era.** AD-5 says `unmapped-<fp8>`; the conventions table and flow diagram say `unmapped_<fp8>`. Hyphens are invalid in BigQuery/Iceberg identifiers used here. Fix: standardize on `unmapped_<fp8>`.

**G7 (low) — Open Q4 (reconcile line-hash algorithm) is a cross-unit divergence point** between the Bronze writer and the reconcile/test code. It is cheap to decide now (for example, reuse sha256 to match `_file_sha256`).

**G8 (low) — Bronze table expiration.** NFR-1 asks for a default Bronze table expiration. AD-3/AD-4 make Bronze the system of record. The spine does not decide this. Fix: state "no Bronze expiration" (upstream PRD update) or decide one.

**G9 (low) — AD-21 "Python 3.12 everywhere" vs Composer image.** The Python version of `composer-3-airflow-3.3.1-build.2` is not verified. The DAG factory in `dags/` may run on a different interpreter. Fix: scope AD-21 to non-Composer units, or verify.

**G10 (low) — Enforceability.** "No CLI apply while a main deploy runs" (AD-18) relies on the state lock, so it is fine, but this should be stated. "Logs are PHI-scanned" (AD-14) needs a named CI check, which is in the Conventions table. Acceptable.

## Upstream PRD update needed (user overrides, not spine defects)

- NFR-7 / prd:371: Fusion is blocking; Core is local fallback only (AD-15). The PRD also requires BashOperator, not Cosmos, for Fusion, and the spine lists cosmos 1.15.1 under flagged. Reconcile in the PRD.
- FR-5 / NFR-1: landing lifecycle is Coldline 7d -> Archive 60d with no delete (AD-3). This replaces the 7-day delete. PRD "documented, not exercised" tiers also change.
- Orchestration: no Airflow by default; local runner default, Composer and Workflows flagged (AD-16, AD-17).
- Dataproc Serverless 3.0 (non-LTS, EOL 2027-01-31) instead of 2.3 LTS (AD-21).
- Bronze is one table per (source, feed, era), not per delivery or 1:1 per file (AD-4).
- D-6 catalog decision resolved as the BigLake REST catalog. Close it in the PRD.
