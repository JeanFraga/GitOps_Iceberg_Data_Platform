# Freshness review — architecture spine (2026-10-07)

## Method
Cross-checked the Stack table and named capabilities against the memlog version sweep wf_5ff86a46-f83 (2026-10-07, supersedes the earlier Oct check), plus spot web searches today (Workflows/Dataproc connectors, Splink 5 backends).

## Verdict
Mostly fresh. All Stack table versions match the same-day web sweep recorded in the memlog. A few capabilities are still unverified, and one runtime choice has a lifecycle risk.

## Findings
1. **[medium] Cloud Workflows waits on Dataproc batches and Cloud Run jobs are unverified** (spine Open Q1, memlog L50). Spot search turned up only community callback/polling patterns, not a first-party connector page. Fix: confirm the `googleapis.dataproc.v1.projects.locations.batches.create` and `googleapis.run.v2...jobs.run` connectors (and whether they wait on long-running operations) before turning on `workflows_enabled`. Low urgency because the flag is off.
2. **[medium] Splink 5.0.0 API and backend are unconfirmed.** The memlog records that the version exists, but the spine never says which backend MPI uses. A search today found no documentation for Splink 5 or for a BigQuery backend (Splink 4 supports DuckDB, Spark, Athena and Postgres). DuckDB 1.5.6 is pinned, so DuckDB is probably intended. Fix: state the backend in AD-14 (DuckDB, or Spark for scale) and check the Splink 5 API against v4 before coding.
3. **[medium] Dataproc Serverless 3.0 is non-LTS with support ending 2027-01-31**, about 4 months from now. Override noted as user choice; Fix: add a deferred-decision row with a trigger to move to the next runtime before EOL.
4. **[low] BigLake REST catalog on runtime 3.0 is only implied.** The memlog confirms REST on 2.3.10 and later, but not a 3.0 + Iceberg 1.12.0 combination. The iceberg-gcp-bundle requirement is also unverified. Fix: run a smoke test early (catalog create, append, read from BigQuery).
5. **[low] spark-bigquery-connector is pinned as "bundled" (0.42.3), but 0.45.0 is the latest.** This is consistent with the "track latest stable" policy only if bundled is a deliberate choice. Fix: note the bundled version explicitly in versions.yaml.
6. **[low] Fusion 2.0.6 BigQuery features are not enumerated.** The spine relies on `static_analysis: strict`, column-level lineage without login, and the MD5 hash. Only "Fusion stable on BigQuery" was checked. Fix: a quick check against Fusion docs of the strict mode and BigQuery adapter coverage of the DV macros. The memlog says 2.0.7 is known bad, so keep the pin.
7. **[low] Python 3.12 is not the latest (3.14.8),** but it is pinned on purpose to match Dataproc 3.0. Fine.

## Upstream PRD update needed (user overrides, not spine defects)
- Fusion is the blocking build (the PRD had dbt Core as blocking).
- Landing lifecycle is Coldline/Archive (the PRD had a 7-day delete).
- No Airflow by default (local runner; Workflows and Composer flagged off).
- Dataproc runtime 3.0.
- Bronze table per (source, feed, era).
