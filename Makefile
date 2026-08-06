.DEFAULT_GOAL := help

help: ## Show available targets
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  %-12s %s\n", $$1, $$2}'

lint: ## Ruff lint for the Spark jobs and Composer DAGs
	ruff check src/spark_jobs src/composer
	find src/composer/dags -name '*.py' -exec python -m py_compile {} +

test: ## PySpark unit + Iceberg integration tests
	pytest src/spark_jobs/tests/ -v

tf-validate: ## Terraform fmt + validate (no cloud credentials needed)
	terraform fmt -check -recursive
	TF_DATA_DIR=.terraform-validate terraform -chdir=infra/environments/dev init -backend=false -input=false > /dev/null
	TF_DATA_DIR=.terraform-validate terraform -chdir=infra/environments/dev validate

tflint: ## TFLint over infra/ (skipped if tflint is not installed)
	@if command -v tflint > /dev/null 2>&1; then \
		cd infra && tflint --init > /dev/null && tflint --recursive --format compact; \
	else \
		echo "tflint not installed; skipping (CI runs it)"; \
	fi

dbt-parse: ## dbt parse check (no BigQuery connection needed)
	cd src/dbt_project && GCP_PROJECT_ID=$${GCP_PROJECT_ID:-dummy-project} dbt parse --profiles-dir .

validate: lint test tf-validate tflint dbt-parse ## Run all local CI-parity checks

.PHONY: help lint test tf-validate tflint dbt-parse validate
