# GitOps Iceberg Data Platform

A production-grade, cost-optimised **Medallion Data Platform** on Google Cloud Platform.  
All data tiers (Bronze / Silver / Gold) live in **Apache Iceberg** format on **GCS**.  
**BigQuery** is used exclusively as a federated query engine via **BigLake** – zero native BQ storage costs.

---

## Architecture

```
NYC TLC Parquet (public)
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
  │  (Iceberg)  │
  └──────┬──────┘
         │  dbt-bigquery  (Gold models)
         ▼
  ┌─────────────┐
  │    GOLD     │  BigQuery external tables (BigLake → GCS Iceberg)
  │ Star Schema │  fact_trips / dim_locations / dim_date
  └─────────────┘
```

### Key Design Decisions
| Concern | Choice |
|---|---|
| Storage | GCS (all layers in Iceberg) |
| Compute – ingestion & ETL | Dataproc Serverless (PySpark) |
| Compute – transformation | dbt-bigquery external tables |
| Query engine | BigQuery (BigLake federated) |
| IaC | Terraform ≥ 1.5 |
| GitOps | Argo CD |
| CI/CD | GitHub Actions |

---

## Repository Structure

```
data-platform-gitops/
├── .devcontainer/           # VS Code / GitHub Codespaces dev environment
├── .github/workflows/
│   ├── terraform.yml        # Terraform validate → plan → apply
│   └── release.yml          # dbt compile + Dataproc batches + dbt run
├── infra/
│   ├── modules/bq_iceberg/  # Reusable Terraform module (GCS + BQ + BigLake)
│   └── environments/dev/    # Dev environment instantiation
├── gitops/
│   ├── apps/                # Argo CD Application YAMLs
│   └── overlays/dev/        # Kustomize overlay for the dev environment
└── src/
    ├── spark_jobs/          # PySpark ETL (Bronze ingestion + Silver MERGE)
    └── dbt_project/         # dbt models (Silver → Gold star schema)
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

---

## Quick-Start (local dev container)

### 1. Open in VS Code Dev Container

```bash
# Open the repo in VS Code, then:
# Command Palette → "Dev Containers: Reopen in Container"
```

All dependencies (Terraform, PySpark, dbt, gcloud) are pre-installed.

### 2. Authenticate to GCP with `GCP_SA_KEY`

```bash
echo "$GCP_SA_KEY" | base64 --decode > /tmp/gcp-sa-key.json
gcloud auth activate-service-account --key-file=/tmp/gcp-sa-key.json
gcloud auth application-default login --cred-file=/tmp/gcp-sa-key.json
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

```bash
spark-submit \
  --packages org.apache.iceberg:iceberg-spark-runtime-3.5_2.12:1.5.2 \
  src/spark_jobs/ingest_bronze.py \
  --project-id $GCP_PROJECT_ID \
  --year 2023 --month 1
```

### 5. Run Silver ETL

```bash
spark-submit \
  --packages org.apache.iceberg:iceberg-spark-runtime-3.5_2.12:1.5.2 \
  src/spark_jobs/bronze_to_silver.py \
  --project-id $GCP_PROJECT_ID
```

### 6. Build Gold Layer (dbt)

```bash
cd src/dbt_project
dbt run  --profiles-dir .
dbt test --profiles-dir .
```

---

## CI/CD Secrets Required

Add the following secrets to your GitHub repository:

| Secret | Description |
|---|---|
| `GCP_PROJECT_ID` | GCP project ID |
| `GCP_SA_KEY` | Base64-encoded service account JSON key used for GitHub Actions and local authentication |
| `PIPELINE_SERVICE_ACCOUNT` | Service account email for Dataproc jobs |

---

## Running Unit Tests (PySpark)

```bash
pip install pyspark pytest
pytest src/spark_jobs/tests/ -v
```

---

## Cost Optimisation Notes

- **Zero BigQuery storage costs** – all data resides on GCS.
- **Iceberg compaction** is run after every Silver MERGE to prevent small-file proliferation.
- **Snapshot expiration** retains the last 5 snapshots by default.
- GCS lifecycle policy moves data to NEARLINE after 90 days.

---

## License

[MIT](LICENSE)