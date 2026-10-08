---
title: 'Ops, steward and mpi_eval datasets and the warehouse store'
type: 'feature'
ticket: '7'
created: '2026-10-08'
status: done
baseline_revision: '05e8fc770009db754326faa6ee87be3e77c42145'
route: 'full'
route_source: 'auto'
risk: 'medium'
review: 'quick'
review_source: 'pinned'
lenses_ran: [quick]
review_loop_iteration: 0
followup_review_recommended: true
context: []
warnings: []
deferred: []
---

<intent-contract>

## Intent

**Problem:** The `ops` dataset (entry 1) has no tables, there are no `steward` or `mpi_eval` datasets, and there is no Iceberg warehouse bucket or BigLake REST catalog. Later entries (10 run-identity stub, ingestion, MPI, steward) need them.

**Approach:** Add a `bq_ops` module that declares tables from `schemas/*.json` into the existing `ops` dataset (passed in by id, not re-declared) and creates the `steward` and `mpi_eval` datasets with their tables. Extend `infra/modules/storage` with the warehouse bucket and a BigLake Iceberg REST catalog on it. Every name derives from `config/resolved.yaml` (`project_id`, `region`). Apply from the CLI.

## Boundaries & Constraints

**Always:**
- The `ops` dataset stays the single `google_bigquery_dataset.ops` in `infra/environments/demo/main.tf`; the module receives its `dataset_id`.
- One JSON schema file per table at `infra/modules/bq_ops/schemas/<dataset>.<table>.json` (BigQuery JSON schema format: name, type, mode, description), loaded with `file()` by a `for_each` over the directory (`fileset`).
- Tables: `ops.file_lifecycle`, `ops.quarantine`, `ops.drift_report`, `ops.run_events`, `ops.run_lock`, `steward.review_queue`, `steward.decision`, `mpi_eval.ground_truth`, `mpi_eval.metrics`. Columns follow the architecture (AD-10, AD-16, AD-17, AD-23, AD-24, AD-25); see Design Notes.
- `ops.run_lock` columns exactly: `lock_key STRING REQUIRED, run_id STRING REQUIRED, acquired_at TIMESTAMP REQUIRED, expires_at TIMESTAMP REQUIRED`.
- `ops.run_events` carries the Dataproc run counter as `dataproc_run_seq INT64 NULLABLE`.
- Datasets and the warehouse bucket in `local.cfg.region` (us-east1); `delete_contents_on_destroy = true`, tables `deletion_protection = false`, bucket `force_destroy = true` (POC teardown, AD-4).
- Warehouse bucket `<project_id>-warehouse`, uniform access, public access prevention enforced; runtime SA gets `roles/storage.objectAdmin` on it (Bronze writer). BigLake catalog: `google_biglake_iceberg_catalog` with `catalog_type = "CATALOG_TYPE_GCS_BUCKET"`, name = warehouse bucket name. Enable `biglake.googleapis.com` with `google_project_service` (`disable_on_destroy = false`) and make the catalog depend on it.
- No hardcoded `us-east1` or project id anywhere under `infra/` (`grep -rn us-east1 infra/` prints nothing outside `.terraform*`).

**Never:**
- No second `google_bigquery_dataset` for `ops`; no Bronze tables or namespaces (ingestion entries own them); no partitioning/clustering decisions beyond `run_events`/`file_lifecycle` day partitioning on their timestamp.
- No IAM changes beyond the runtime SA on the warehouse bucket.

</intent-contract>

## Code Map

- `infra/environments/demo/main.tf` -- `locals.cfg` from resolved.yaml; `google_bigquery_dataset.ops` (keep); add `module "bq_ops"`, pass `module.iam.runtime_sa_member` into storage (already); add outputs `warehouse_bucket`, `iceberg_catalog`, `steward_dataset_id`, `mpi_eval_dataset_id`.
- `infra/modules/storage/{main,variables,outputs}.tf` -- landing bucket pattern to mirror for warehouse; `required_providers google >= 8.6.0`.
- `infra/modules/iam/outputs.tf` -- `runtime_sa_member`.
- `Makefile` -- `tf-bootstrap` (owner apply, `-auto-approve`), `tf-validate`, `tflint`, `validate`. Deploy SA lacks BigLake roles, so apply with `make tf-bootstrap`.
- `infra/environments/demo/.terraform-validate/` -- local validate cache, do not edit.

## Tasks & Acceptance

**Execution:**
- [x] `infra/modules/bq_ops/schemas/*.json` -- create the nine schema files -- single source of table shape.
- [x] `infra/modules/bq_ops/{main,variables,outputs}.tf` -- inputs `project_id`, `region`, `ops_dataset_id`; create `steward` and `mpi_eval` datasets; `for_each` over `fileset(schemas, "*.json")` keyed `<dataset>.<table>` creating `google_bigquery_table` in the right dataset -- one generic table resource.
- [x] `infra/modules/storage/*.tf` -- warehouse bucket, runtime objectAdmin binding, `biglake.googleapis.com` service, `google_biglake_iceberg_catalog`; outputs `warehouse_bucket`, `iceberg_catalog`.
- [x] `infra/environments/demo/main.tf` -- wire module and outputs.
- [x] `infra/modules/bq_ops/check_schemas.sh` -- for each schema file, `bq show --schema --format=prettyjson <project>:<dataset>.<table>` and diff against the file normalized with `jq -S '[.[]|{name,type,mode:(.mode//"NULLABLE")}]'` on both sides; exit non-zero on any diff; reads project from `config/resolved.yaml`.

**Acceptance Criteria:**
- Given the code on main, when `make tf-bootstrap` runs, then apply completes with no errors and a second plan shows no changes.
- Given the apply, when `infra/modules/bq_ops/check_schemas.sh` runs, then every declared table diffs clean and the script exits 0.
- Given the apply, when `gcloud storage buckets describe gs://<project>-warehouse --format='value(location)'` runs, then it prints `US-EAST1`, and the BigLake catalog named after the bucket exists.

## Implementation Notes

- `check_schemas.sh` maps INT64->INTEGER, FLOAT64->FLOAT, BOOL->BOOLEAN on both sides, since `bq show` reports legacy type names.
- Applied 2026-10-08 via `make tf-bootstrap` (15 added); re-plan shows no changes; check_schemas exits 0; warehouse location US-EAST1.

## Plan Change Log

## Review Triage Log

### 2026-10-08 — Review pass
- verdicts: 3 findings — high 1, medium 0, low 2, false 0, maybe-false 0
- findings:
  - `[low]` `[patch]` storage `runtime_member` description and module header still describe landing-only access — updated both to mention warehouse objectAdmin.
  - `[high]` `[patch]` schema JSON files absent from the diff; `.gitignore` blanket `*.json` would drop them, so a fresh checkout plans to destroy all nine tables — added `!infra/modules/bq_ops/schemas/*.json` negation next to the devcontainer one.
  - `[low]` `[reject]` `check_schemas.sh` reads project_id with sed — resolved.yaml is generated by config/load.py with an unquoted value; a parser fix adds complexity for an unlikely case.

## Design Notes

Columns (all REQUIRED unless noted NULLABLE):
- `file_lifecycle`: file_sha256, object_uri, source, feed, state (lifecycle enum), run_id, recorded_at TIMESTAMP, storage_class NULLABLE, detail NULLABLE JSON.
- `quarantine`: file_sha256, line_ordinal INT64 NULLABLE, reason, raw_line NULLABLE, run_id, quarantined_at TIMESTAMP.
- `drift_report`: run_id, source, feed, schema_era, drift_kind, detail JSON NULLABLE, mode, reported_at TIMESTAMP.
- `run_events`: event_id, run_id, task NULLABLE, event (e.g. started, mpi_complete, finished), executor NULLABLE, dataproc_run_seq INT64 NULLABLE, detail JSON NULLABLE, event_at TIMESTAMP.
- `review_queue`: candidate_id, pair_hk, scores JSON, model_version, run_id, queued_at TIMESTAMP.
- `decision`: decision_id, pair_hk, decision, scores_at_decision JSON, model_version, reason NULLABLE, os_user, host, decided_at TIMESTAMP, supersedes NULLABLE.
- `ground_truth`: generator_seed INT64, source_record_id, source, person_truth.
- `metrics`: run_id, model_version, threshold_set_version, eval_seed INT64, metric, value FLOAT64, computed_at TIMESTAMP.

## Verification

**Commands:**
- `make tf-validate && make tflint` -- expected: pass.
- `make tf-bootstrap` -- expected: `Apply complete!`, no errors.
- `terraform -chdir=infra/environments/demo plan -detailed-exitcode -input=false` -- expected: exit 0.
- `bash infra/modules/bq_ops/check_schemas.sh` -- expected: exit 0.
- `grep -rn us-east1 infra/ --exclude-dir='.terraform*'` -- expected: no output.

## Auto Run Result

- **Summary:** Added the `bq_ops` module (steward and mpi_eval datasets, nine tables from `schemas/*.json` in ops/steward/mpi_eval), the `<project>-warehouse` bucket, runtime objectAdmin on it, the BigLake API and the `CATALOG_TYPE_GCS_BUCKET` Iceberg catalog. Applied with `make tf-bootstrap` (15 added).
- **Files:** `infra/modules/bq_ops/*` (new module, schemas, check script); `infra/modules/storage/{main,outputs,variables}.tf` (warehouse + catalog); `infra/environments/demo/main.tf` (wiring, outputs); `.gitignore` (track schema JSON).
- **Review:** 2 patched (1 high, 1 low), 0 deferred, 1 rejected (sed parsing of generated resolved.yaml; unlikely, fix adds complexity).
- **Follow-up review recommended:** true. The high patch was a `.gitignore` negation; the remaining risk is that it is not confirmed that `git ls-files infra/modules/bq_ops/schemas` lists all nine files after the commit.
- **Verification:** tf-validate pass; apply complete; re-plan no changes; check_schemas.sh OK for 9 tables; warehouse in US-EAST1; no hardcoded us-east1.
- **Residual risk:** `make tf-plan`/`tf-apply` as the deploy SA lack BigLake permissions; owner `tf-bootstrap` was used.
