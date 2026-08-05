# GitOps Iceberg Data Platform

A production-grade, cost-optimised **Medallion Data Platform** on Google Cloud Platform.
**Bronze** and **Silver** tiers live in **Apache Iceberg** format on **GCS**; BigQuery
federates the Silver tier via **BigLake** external tables, and **dbt** materialises the
**Gold** star schema as native BigQuery tables.

---

## Architecture

```
NYC TLC Parquet (public, staged to GCS)
        │
        ▼  ingest_bronze.py  (Dataproc Serverless)
  ┌─────────────┐
  │   BRONZE    │  GCS: .../warehouse/bronze/yellow_trips/
  │  (Iceberg)  │
  └──────┬──────┘
         │  bronze_to_silver.py  (Dataproc Serverless)
         ▼   MERGE INTO + compaction + snapshot expiry
  ┌─────────────┐
  │   SILVER    │  GCS: .../warehouse/silver/yellow_trips/
  │  (Iceberg)  │  + BigQuery external table (BigLake → GCS)
  └──────┬──────┘
         │  dbt-bigquery  (Gold models)
         ▼
  ┌─────────────┐
  │    GOLD     │  BigQuery native tables (dbt-managed)
  │ Star Schema │  fact_trips / dim_locations / dim_date
  └─────────────┘
```

### Key Design Decisions
| Concern | Choice |
|---|---|
| Storage – Bronze/Silver | GCS (Apache Iceberg) |
| Compute – ingestion & ETL | Dataproc Serverless (PySpark) |
| Compute – transformation | dbt-bigquery (Gold as native BQ tables) |
| Silver query access | BigQuery via BigLake external table |
| IaC | Terraform ≥ 1.5 |
| CI/CD | GitHub Actions |
| GitOps | Argo CD (scaffolding only — see [GitOps status](#gitops-status)) |

---

## Repository Structure

```
GitOps_Iceberg_Data_Platform/
├── .devcontainer/           # VS Code / Codespaces dev environment
├── .github/
│   ├── dependabot.yml       # Automated dependency updates
│   └── workflows/
│       ├── terraform.yml    # Terraform fmt/validate/tflint → plan → apply
│       └── release.yml      # Validate (lint+tests+dbt parse) → Dataproc batches → dbt
├── infra/
│   ├── modules/bq_iceberg/  # Reusable Terraform module (GCS + BQ datasets + BigLake)
│   └── environments/dev/    # Dev environment instantiation
├── gitops/
│   ├── apps/                # Argo CD Application YAMLs (scaffolding)
│   └── overlays/dev/        # Kustomize overlay for the dev environment
├── scripts/
│   └── validate-local.sh    # Local Terraform-workflow reproduction (needs GCP auth)
├── src/
│   ├── spark_jobs/          # PySpark ETL (common.py + Bronze ingestion + Silver MERGE)
│   └── dbt_project/         # dbt models (staging → Gold star schema) + seeds
└── Makefile                 # Local CI-parity tasks (make help)
```

---

## Prerequisites

| Tool | Version |
|---|---|
| Terraform | ≥ 1.5 |
| Python | 3.11 |
| Java | 17 (for local PySpark) |
| gcloud CLI | latest |
| dbt-bigquery | ≥ 1.7 |
| PySpark | 3.5.x |

A **Terraform state bucket** must exist before the first `terraform init` — it is
created out-of-band because Terraform cannot manage its own state store:

```bash
gcloud storage buckets create gs://gitops-iceberg-data-platform-tfstate \
  --location=us-east1 --uniform-bucket-level-access
```

(The bucket name is configured in `infra/environments/dev/main.tf`.)

---

## Quick-Start (local dev container)

### 1. Open in VS Code Dev Container

```bash
# Open the repo in VS Code, then:
# Command Palette → "Dev Containers: Reopen in Container"
```

PySpark, dbt, and Java are baked into the image; Terraform and gcloud are added
by dev-container features (see `.devcontainer/devcontainer.json`).

### 2. Authenticate to GCP

```bash
# With your own service-account key file (raw JSON):
gcloud auth activate-service-account --key-file=/path/to/key.json
gcloud auth application-default login --cred-file=/path/to/key.json
export GCP_PROJECT_ID=your-gcp-project-id
```

### 3. Deploy Infrastructure

```bash
cd infra/environments/dev
terraform init
terraform plan   -var="project_id=$GCP_PROJECT_ID" -var-file=dev.tfvars
terraform apply  -var="project_id=$GCP_PROJECT_ID" -var-file=dev.tfvars
```

### 4. Ingest Bronze Data

The job reads from GCS (Spark has no HTTP driver), so stage the public TLC
file first. Two local-run notes:

- The Iceberg package below uses the **Scala 2.12** build — pip-installed
  PySpark ships Scala 2.12, unlike the Dataproc runtime used in CI (Scala
  2.13; see `ICEBERG_SPARK_PACKAGE` in `.github/workflows/release.yml`).
- pip PySpark has no `gs://` filesystem, so the **GCS connector jar** is added
  with `--jars`; it authenticates via the Application Default Credentials set
  up in step 2.

```bash
GCS_CONNECTOR=https://storage.googleapis.com/hadoop-lib/gcs/gcs-connector-hadoop3-latest.jar

SRC=yellow_tripdata_2023-01.parquet
curl -fsSL "https://d37ci6vzurychx.cloudfront.net/trip-data/${SRC}" -o "${SRC}"
gsutil cp "${SRC}" "gs://${GCP_PROJECT_ID}-iceberg-warehouse/landing/${SRC}"

spark-submit \
  --packages org.apache.iceberg:iceberg-spark-runtime-3.5_2.12:1.5.2 \
  --jars "${GCS_CONNECTOR}" \
  --py-files src/spark_jobs/common.py \
  src/spark_jobs/ingest_bronze.py \
  --project-id $GCP_PROJECT_ID \
  --source-uri "gs://${GCP_PROJECT_ID}-iceberg-warehouse/landing/${SRC}" \
  --period 2023-01
```

`--period` scopes the write to the file's nominal month so stray out-of-month
rows cannot overwrite other months' partitions.

### 5. Run Silver ETL

```bash
spark-submit \
  --packages org.apache.iceberg:iceberg-spark-runtime-3.5_2.12:1.5.2 \
  --jars "${GCS_CONNECTOR}" \
  --py-files src/spark_jobs/common.py \
  src/spark_jobs/bronze_to_silver.py \
  --project-id $GCP_PROJECT_ID
```

### 6. Build Gold Layer (dbt)

```bash
cd src/dbt_project
dbt seed --profiles-dir .   # loads the TLC taxi-zone lookup
dbt run  --profiles-dir .
dbt test --profiles-dir .
```

---

## CI/CD

Two GitHub Actions workflows:

- **`terraform.yml`** — on changes under `infra/`: fmt + validate + tflint, plan
  (posted to PRs), and apply on `main`.
- **`release.yml`** — on changes under `src/`: a `validate` job (ruff, dbt parse,
  PySpark unit + Iceberg integration tests) runs on every PR and push; on `main`
  it continues into Dataproc Serverless batches (Bronze, Silver), registers the
  Silver BigLake table, and runs `dbt seed/run/test`. Historical months can be
  backfilled via `workflow_dispatch` (`ingest_year`/`ingest_month`) — submit
  backfills **one at a time**: the concurrency group holds a single pending
  slot, so a newly queued dispatch silently evicts an already-queued one.

### Secrets Required

| Secret | Description |
|---|---|
| `GCP_PROJECT_ID` (or `TF_VAR_PROJECT_ID`) | GCP project ID |
| `GCP_SA_KEY` | Service account JSON key (raw JSON, **not** base64) used by GitHub Actions |
| `PIPELINE_SERVICE_ACCOUNT` | Service account email for Dataproc jobs |

---

## Local Validation

```bash
make help       # list available tasks
make validate   # ruff + pytest + terraform fmt/validate + dbt parse (no GCP auth needed)
```

`scripts/validate-local.sh` additionally reproduces the Terraform workflow
(init/plan against the real backend) and requires a `.env` file plus GCP
credentials — see `.env.example`.

Running the tests directly:

```bash
pip install -r src/spark_jobs/requirements.txt
pytest src/spark_jobs/tests/ -v
```

The integration tests download the Iceberg runtime jar from Maven Central on
first run and exercise real table DDL, writes, and MERGE against a local
warehouse directory.

---

## GitOps Status

The `gitops/` tree (Argo CD `Application` + Kustomize overlay) is **scaffolding
for a future GKE-based deployment** — no Kubernetes workload currently consumes
the ConfigMap it defines, and CI does not deploy it. Treat the values in
`gitops/overlays/dev/config.yaml` as documentation until it is wired to a
cluster.

---

## Cost Optimisation Notes

- **Bronze/Silver storage on GCS** – no native BigQuery storage for the large
  trip-level tiers; Silver is queried through BigLake federation.
- **Gold** – small star-schema tables materialised natively in BigQuery by dbt.
- **Iceberg compaction** runs after every Silver MERGE to prevent small-file
  proliferation.
- **Snapshot expiration** retains the last 5 snapshots by default.
- GCS lifecycle policy moves data to NEARLINE after 90 days.

---

## License

[MIT](LICENSE)
