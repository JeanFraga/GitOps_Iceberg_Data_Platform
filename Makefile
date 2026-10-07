.DEFAULT_GOAL := help

PROFILE ?= demo

help: ## Show available targets
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  %-12s %s\n", $$1, $$2}'

resolve: ## Resolve config (defaults + PROFILE + versions.yaml) into config/resolved.yaml
	uv run python config/load.py --profile $(PROFILE)

validate-config: ## Validate defaults and every profile (demo, _template) against the JSON Schema
	@for p in demo _template; do uv run python config/load.py --profile $$p --validate-only || exit 1; done

check-resolved: ## Fail if config/resolved.yaml is stale or hand-edited (CI calls this)
	uv run python config/load.py --profile $(PROFILE) --check

lint: ## Ruff lint + format check over Python sources
	uv run ruff check .
	uv run ruff format --check .

test: ## Pytest (config loader and later suites)
	uv run pytest

tf-validate: ## Terraform fmt + validate (no cloud credentials needed)
	terraform fmt -check -recursive
	TF_DATA_DIR=.terraform-validate terraform -chdir=infra/environments/demo init -backend=false -input=false > /dev/null
	TF_DATA_DIR=.terraform-validate terraform -chdir=infra/environments/demo validate

tflint: ## TFLint over infra/ (skipped if tflint is not installed)
	@if command -v tflint > /dev/null 2>&1; then \
		cd infra && tflint --init > /dev/null && tflint --recursive --format compact; \
	else \
		echo "tflint not installed; skipping"; \
	fi

validate: lint test validate-config check-resolved tf-validate tflint ## Run all local checks (later entries append targets here)

.PHONY: help resolve validate-config check-resolved lint test tf-validate tflint validate
