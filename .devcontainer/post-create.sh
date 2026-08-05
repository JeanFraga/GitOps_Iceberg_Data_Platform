#!/usr/bin/env bash
# post-create.sh – runs once after the dev container is built
set -euo pipefail

echo "==> Installing Python dependencies …"
pip install --no-cache-dir \
    pyspark==3.5.1 \
    "dbt-core>=1.7,<2.0" \
    "dbt-bigquery>=1.7,<2.0" \
    pytest \
    black \
    ruff

echo "==> Verifying dbt installation …"
dbt --version

echo "==> Verifying PySpark installation …"
python -c "import pyspark; print('PySpark', pyspark.__version__)"

echo "==> Dev container setup complete."
echo ""
echo "Quick-start:"
echo "  1. Set GCP_PROJECT_ID:  export GCP_PROJECT_ID=your-project"
echo "  2. Authenticate:        gcloud auth application-default login"
echo "  3. Deploy infra:        cd infra/environments/dev && terraform init && terraform apply -var-file=dev.tfvars"
echo "  4. Ingest Bronze:       spark-submit src/spark_jobs/ingest_bronze.py --project-id \$GCP_PROJECT_ID"
echo "  5. Run Silver ETL:      spark-submit src/spark_jobs/bronze_to_silver.py --project-id \$GCP_PROJECT_ID"
echo "  6. Run dbt Gold layer:  cd src/dbt_project && dbt run --profiles-dir ."
