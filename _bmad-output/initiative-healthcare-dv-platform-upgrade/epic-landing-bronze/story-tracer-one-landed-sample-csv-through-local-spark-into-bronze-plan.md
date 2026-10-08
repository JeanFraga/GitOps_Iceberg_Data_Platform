---
title: 'Tracer: one landed sample CSV through local Spark into Bronze Iceberg, read from BigQuery'
type: 'feature'
ticket: '1'
created: '2026-10-08'
status: 'in-progress'
baseline_revision: 'c3f96e8079bf707a007a9cdd1d0fb515364244ee'
route: 'full'
route_source: 'auto'
risk: 'high'
review: ''
review_source: ''
lenses_ran: []
review_loop_iteration: 0
followup_review_recommended: false
context:
  - '{project-root}/_bmad-output/initiative-healthcare-dv-platform-upgrade/epic-landing-bronze/epic-landing-bronze.md'
warnings: []
deferred: []
---

<intent-contract>

## Intent

**Problem:** There is no Bronze layer: nothing loads a landed file into Iceberg. Also unverified is whether BigLake REST works with Iceberg 1.12.0 on Spark 4.0 / runtime 3.0 (OQ 2, 3 and 5).

**Approach:** Add local Spark 4.0 (Java 21) and an `ingestion/` package, run by `make bronze PROFILE=demo FILE=gs://...`. It refuses an unmarked object, drops the CSV marker line, and appends all-STRING rows plus lineage columns to `bronze_payer_b.members__<fixed era>` in the BigLake REST catalog. It writes `landed` then `bronze_appended` to `ops.file_lifecycle`, then proves a BigQuery read.

## Boundaries & Constraints

**Always:**
- The pins are pyspark 4.0.x, Java 21 and `iceberg-spark-runtime-4.0_2.13:1.12.0`, from versions.yaml.
- `run_id` comes from `pipeline.runner.mint_run_id` (AD-24), which the runner path passes into the task.
- Every `bq` call carries `--project_id` and `--maximum_bytes_billed` from resolved.yaml.
- Logs and errors never contain row values.
- Use non-interactive CLI flags (`--quiet`, `-auto-approve`).
- Never update or delete Bronze rows, and never run expire_snapshots.

**Never:**
- No WAP or reconcile (that is entry 2).
- No fingerprint routing (entry 3); the era is fixed as `members__era_2024`, still computed via `config/fingerprint.py` and recorded in detail.
- No discovery or duplicate handling (entry 4).
- No NDJSON or X12 loading (entry 5).
- If create, append or the BigQuery read fails on the pinned versions, change no pin. Record the finding and stop: the ticket is blocked.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|---|---|---|---|
| HAPPY_PATH | marked CSV (marker line, header, N rows) | N Bronze rows, `_line_ordinal` 3..N+2, `_raw_line` = exact line text; lifecycle `landed`, `bronze_appended` | none |
| UNMARKED | no marker token within `within_bytes` | refused, nonzero exit, structured JSON log line, no Bronze write, no lifecycle row | `UnmarkedFile` error |
| MARKER_DROP | marker present as line 1 | header = line 2; the fingerprint is over the text without the marker line | — |
| BOM | UTF-8 BOM before marker | BOM stripped before the marker check and split | — |
| CRLF | lines ending CRLF | `_raw_line` excludes the terminator | — |

</intent-contract>

## Code Map

- `versions.yaml`: add pins `spark: "4.0.x"` (the exact pyspark version), `java: "21"`, and `iceberg_gcp_bundle` only if needed. These pins flow to `config/resolved.yaml` through `config/load.py`. Run `make resolve` afterwards so `make check-resolved` passes.
- `pyproject.toml`: add a `pyspark==4.0.*` exact pin to the dependencies, and add `ingestion` to pytest `testpaths`. Then `uv lock`.
- `.devcontainer/Dockerfile`: replace `default-jdk-headless` with `openjdk-21-jdk-headless`, with JAVA_HOME at `/usr/lib/jvm/java-21-openjdk-amd64`. Also install Java 21 in the current container with `sudo apt-get install -y`, and make it the default via `JAVA_HOME`/PATH (or update-alternatives).
- `config/standards/records.yaml` (new): the AD-4 record split per format:
  - csv and jsonl split on LF (RFC 4180 quoting for csv)
  - x12 splits on ISA16
  - `strip_bom: true`
  - non-UTF-8 records are stored base64 with a `_raw_encoding` flag
  
  If load.py validates standards, add a schema next to `config/schemas/`.
- `config/fingerprint.py`: reuse `fingerprint(text, "csv")` and `fp8`. Do not modify it.
- `config/standards/guardrails.yaml`: the `synthetic_marker.token` and `within_bytes` settings. Read them; do not modify.
- `config/standards/lifecycle.yaml`: the states. Read only.
- `pipeline/runner.py`:
  - Reuse `mint_run_id` and `BigQueryBackend`.
  - Add an option so `run()` executes a supplied task callable instead of `noop_task`, without breaking the existing tests.
  - Also add a thin `ops.run_events` writer only if that is trivial; otherwise skip it.
- `infra/modules/bq_ops/schemas/ops.file_lifecycle.json`: the columns. `detail` is JSON.
- `infra/modules/storage/main.tf`: has the existing `google_biglake_iceberg_catalog.warehouse`, named `${project_id}-warehouse`. The REST endpoint is `https://biglake.googleapis.com/iceberg/v1/restcatalog` with warehouse `gs://${project_id}-warehouse`.
- `infra/modules/iam`: grant the runtime SA what BigLake needs (for example `roles/biglake.editor` and `roles/serviceusage.serviceUsageConsumer`). Apply with `terraform apply -auto-approve` in `infra/environments/demo`. Local runs use user ADC, which owns the project.
- `datagen/upload.py`: the landing layout is `source=/feed=/ingest_date=/sha256=/<name>`. Reuse its helpers to land the tracer file.
- `ingestion/` (new package):
  - `__init__.py`
  - `records.py`: split and BOM handling per records.yaml
  - `marker.py`: the marker check and marker-line drop
  - `bronze.py`: builds the SparkSession with the Iceberg REST catalog via `spark.jars.packages` from versions.yaml, the `google` auth manager, and `header.x-goog-user-project`. It also creates the namespace and the table partitioned by `days(_ingested_at)`, and appends.
  - `lifecycle.py`: writes `ops.file_lifecycle` with `bq query` INSERT
  - `__main__.py`: CLI `--profile --file`
  - `tests/`
- `Makefile`: add the `bronze: resolve` target, which runs `uv run python -m ingestion --profile $(PROFILE) --file $(FILE)` and errors if FILE is empty. Add a `bronze-tracer-land` helper that lands the sample.

## Tasks & Acceptance

**Execution:**
- [x] `versions.yaml`, `pyproject.toml`, `uv.lock`, `.devcontainer/Dockerfile` -- pins and Java 21 -- match Dataproc runtime 3.0 (AD-17).
- [x] `config/standards/records.yaml` -- AD-4 split rules -- shared by the loader and entry 2's reconcile.
- [x] `ingestion/records.py`, `ingestion/marker.py` -- split, BOM, marker refusal and drop -- pure Python, unit-testable without Spark.
- [x] `ingestion/bronze.py`, `ingestion/lifecycle.py`, `ingestion/__main__.py` -- Spark append and lifecycle rows -- the tracer path.
- [x] `pipeline/runner.py` -- run a supplied task with the minted run_id -- AD-24.
- [ ] `infra/modules/iam/*` -- BigLake roles for the runtime SA; apply to demo.
- [x] `Makefile` -- `bronze` target (and the tracer-land helper).
- [x] `ingestion/tests/` -- every matrix row, plus a local-Spark test that appends to a Hadoop-catalog Iceberg table in tmp_path. Mark it skip if Java is missing; it must actually run here.
- [x] Live run on demo: land the sample with `gcloud storage cp --if-generation-match=0`, run `make bronze`, then query from BigQuery. Record the OQ 2/3/5 answers under Implementation Notes: the versions used, whether the gcp bundle was needed, and the BigQuery read path used (for example the `project.catalog.namespace.table` four-part name or a BigLake table).

**Acceptance Criteria:**
- Given the landed sample, when `make bronze PROFILE=demo FILE=gs://.../payer_b_members_2024.csv` runs, then it exits 0. A `bq query` row count on the Bronze table equals 720 (722 lines minus the marker and header lines), with `min(_line_ordinal)` = 3.
- Given that run, when `ops.file_lifecycle` is queried by the file's sha256, then it shows `landed` and `bronze_appended` with the same run_id.
- Given the devcontainer, when `java -version` runs, then it reports 21.
- Given `uv run pytest ingestion`, then the marker-drop and refusal tests pass.

## Implementation Notes

Live run on demo, 2026-10-08, run `20261008T221028Z-e24e2729`: `make bronze PROFILE=demo FILE=gs://gitops-iceberg-data-platform-landing/source=payer_b/feed=members/ingest_date=2026-10-08/sha256=6b79bc0b9e8476901ed9a60f2707a4269df2e6288e5f1ea4e3bedf314fe7b10d/payer_b_members_2024.csv` exited 0; BigQuery count 720, `min(_line_ordinal)` 3; `ops.file_lifecycle` shows `landed` and `bronze_appended` with that run_id (snapshot 8425262399054152884, fp8 `2f7434da`).

OQ 2/3/5 answers:
- Versions: pyspark 4.0.4 (Spark 4.0), Temurin Java 21.0.12, `iceberg-spark-runtime-4.0_2.13:1.12.0`. Create, append and the BigQuery read all work on the pinned versions; no pin was changed.
- GCP bundle: needed. Without `org.apache.iceberg:iceberg-gcp-bundle:1.12.0`, `GoogleAuthManager` fails with `NoClassDefFoundError: com/google/auth/oauth2/GoogleCredentials`. Pinned as `iceberg_gcp_bundle` in versions.yaml.
- Catalog conf: `type=rest`, `uri=https://biglake.googleapis.com/iceberg/v1/restcatalog`, `warehouse=gs://<project>-warehouse`, `rest.auth.type=org.apache.iceberg.gcp.auth.GoogleAuthManager`, `io-impl=org.apache.iceberg.gcp.gcs.GCSFileIO`, `header.x-goog-user-project=<project>`; user ADC.
- BigQuery read path: the four-part name `` `<project>.<project>-warehouse.<namespace>.<table>` `` (catalog = warehouse bucket name), no BigLake table DDL needed.
- Finding: BigLake rejects column names starting with `_file_` (BigQuery reserved prefix) with an opaque `BadRequestException: Malformed request: Request contains an invalid argument`. The lineage column is `_landed_sha256`, not `_file_sha256`. Later lineage/vault columns must avoid BigQuery reserved prefixes (`_FILE_`, `_PARTITION`, `_TABLE_`, `_ROW_TIMESTAMP`, `__ROOT__`, `_COLIDENTIFIER`).

Other notes:
- `pipeline/runner.py` `BigQueryBackend` fixes found by the first live use: it now passes `--project_id`, and it no longer parses DML status output (`Number of affected rows`) as JSON, which had left a lock row held after a failed acquire.
- Three extra `landed` rows (runs 220556Z, 220627Z, 220818Z) were written by failed debugging runs before the fixes; left in place (append-only log; entry 4 handles repeat landed rows).
- Lineage columns: `_raw_line`, `_raw_encoding`, `_line_ordinal`, `_ingested_at`, `_source_file`, `_record_source`, `_landed_sha256`, `_run_id`; snapshot summary carries `run_id`.
- IAM grant (`roles/biglake.editor`, `roles/serviceusage.serviceUsageConsumer` for runtime-sa) is in Terraform and plans cleanly (2 add, plus the pending additive `mpi_eval.ground_truth` column from c3f96e8), but is NOT applied: the demo state has a stale lock (ID 1791492655983054, plan from 2026-10-08 20:50 UTC) and the apply was not run. Local runs use user ADC and did not need it.

## Plan Change Log

- 2026-10-08: Debian bookworm main has no `openjdk-21-jdk-headless`; the Dockerfile installs `temurin-21-jdk` from the Adoptium apt repo instead (JAVA_HOME `/usr/lib/jvm/temurin-21-jdk-amd64`). The running container got the same package via apt and update-alternatives; `/usr/lib/jvm/default-java` was repointed to it.
- 2026-10-08: lineage column `_file_sha256` renamed `_landed_sha256` (BigQuery reserved prefix, see Implementation Notes).

## Review Triage Log

## Design Notes

Treat `_line_ordinal` as a 1-based physical line in the landed file: the marker is line 1, the header line 2, and the first data row line 3. Treat `_ingested_at` as one timestamp per run. `_record_source` is `payer_b.members`, and `_source_file` is the gs:// URI. Do the CSV parsing in Python with the `csv` module, so that `_raw_line` and the ordinals are exact, then create the Spark DataFrame from the rows. The tracer runs at sample scale, and entry 5 or the Dataproc work can revisit this.

## Verification

**Commands:**
- `uv run pytest ingestion pipeline config` -- expected: all pass, with the Spark test not skipped
- `make validate` -- expected: passes (lint, check-resolved, marker-check, repo-weight)
- `java -version` -- expected: 21
- `make bronze PROFILE=demo FILE=<landed uri>` and then `bq query --project_id=gitops-iceberg-data-platform --use_legacy_sql=false --maximum_bytes_billed=10737418240 '<count>'` -- expected: 720 rows; lifecycle shows landed and bronze_appended
