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

# The ticket's interface is `make phi-scan PATH=dir`, which overrides make's own PATH for
# recipes. Only then do recipes run uv with a fixed system PATH (devcontainer and CI locations).
SCAN_PATH := $(if $(filter command line,$(origin PATH)),$(PATH),)
TOOL_PATH := /usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin:$(HOME)/.local/bin:$(HOME)/.cargo/bin
GUARD = $(if $(SCAN_PATH),/usr/bin/env PATH="$(TOOL_PATH)") uv run python tools/guardrails.py

phi-scan: ## FR-35: fail on PHI-shaped values (SSN, generated names). PATH=dir, default repo
	$(GUARD) phi-scan $(SCAN_PATH)

marker-check: ## AD-14: fail on data files without the synthetic marker. PATH=dir, default repo
	$(GUARD) marker-check $(SCAN_PATH)

upgrade: ## Manual platform upgrade (AD-20/FR-40): prints the platform-upgrade skill invocation
	@echo "Platform upgrades run through the Claude Code skill .claude/skills/platform-upgrade."
	@echo "In Claude Code, run:  /platform-upgrade"
	@echo "Scope one component with an argument, e.g.  /platform-upgrade terraform 1.16.5"
	@echo "Then: make validate && make tf-plan (no stateful replacements), commit one change set."

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

validate: lint test validate-config check-resolved phi-scan marker-check tf-validate tflint ## Run all local checks (later entries append targets here)

.PHONY: help upgrade phi-scan marker-check resolve validate-config check-resolved lint test tf-validate tflint validate
