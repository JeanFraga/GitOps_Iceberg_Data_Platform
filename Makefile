.DEFAULT_GOAL := help

PROFILE ?= demo

help: ## Show available targets
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  %-12s %s\n", $$1, $$2}'

# The ticket's interface is `make phi-scan PATH=dir`, which overrides make's own PATH for
# recipes. Only then do recipes run uv with a fixed system PATH (devcontainer and CI locations).
SCAN_PATH := $(if $(filter command line,$(origin PATH)),$(PATH),)
TOOL_PATH := /usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin:$(HOME)/.local/bin:$(HOME)/.cargo/bin
# Same guard for every uv recipe, so targets keep finding uv when a caller overrides PATH.
UV = $(if $(SCAN_PATH),/usr/bin/env PATH="$(TOOL_PATH)") uv
GUARD = $(UV) run python tools/guardrails.py

resolve: ## Resolve config (defaults + PROFILE + versions.yaml) into config/resolved.yaml
	$(UV) run python config/load.py --profile $(PROFILE)

validate-config: ## Validate defaults and every profile (demo, _template) against the JSON Schema
	@for p in demo _template; do $(UV) run python config/load.py --profile $$p --validate-only || exit 1; done

lint-bytes-cap: ## AD-16: fail when PROFILE (name or yaml path) sets no cost.max_bytes_billed
	$(UV) run python config/load.py --profile $(PROFILE) --check-bytes-cap

check-resolved: ## Fail if config/resolved.yaml is stale or hand-edited (CI calls this)
	$(UV) run python config/load.py --profile $(PROFILE) --check

phi-scan: ## FR-35: fail on PHI-shaped values (SSN, generated names; uses datagen/out/names.txt when present). PATH=dir, default repo
	$(GUARD) phi-scan $(SCAN_PATH) $(if $(wildcard datagen/out/names.txt),--names-file datagen/out/names.txt)

marker-check: ## AD-14: fail on data files without the synthetic marker. PATH=dir, default repo
	$(GUARD) marker-check $(SCAN_PATH)

VOLUME ?=

generate: resolve ## Seeded synthetic data (VOLUME=ci -> datagen/out/; VOLUME=full -> estimate, budget guard, land in gs://$PROJECT-landing/, FORCE=1 overrides guard; EVAL=1 held-out eval seed)
	$(UV) run python -m datagen generate $(if $(VOLUME),--volume $(VOLUME)) $(if $(EVAL),--eval) $(if $(FORCE),--force)

generate-upload: resolve ## Land datagen/out/ (VOLUME=ci output; stale after a VOLUME=full run) in the landing bucket and load mpi_eval.ground_truth
	$(UV) run python -m datagen upload

samples: resolve ## FR-37: regenerate committed datagen/samples/ (repo_weight.sample_records per file, deterministic)
	$(UV) run python -m datagen samples

repo-weight: ## FR-37: fail on committed data files over the record/byte limit outside datagen/samples/. PATH=dir
	$(GUARD) repo-weight $(SCAN_PATH)

edi-preparse-check: ## AD-4: regenerate the X12 pre-parse twice per sample; fail on any diff vs ingestion/edi/tests/golden/
	$(UV) run python -m ingestion.edi.check

FILE ?=
TRACER_SAMPLE := datagen/samples/payer_b/members/payer_b_members_2024.csv

SRC ?=

bronze: resolve ## Load landed files into Bronze Iceberg and ops.file_lifecycle. FILE=gs://... for one; empty FILE discovers all pending
	$(UV) run python -m ingestion --profile $(PROFILE) $(if $(FILE),--file $(FILE)) $(if $(TABLE_SUFFIX),--table-suffix $(TABLE_SUFFIX))

reconcile-storage: resolve ## Record landing storage-class moves (STANDARD/COLDLINE/ARCHIVE) in ops.file_lifecycle
	$(UV) run python -m ingestion.storage_class --profile $(PROFILE)

land: resolve ## Land SRC/<source>/<feed>/<file> immutably under AD-3 (overwrite rejected and logged). SRC=dir required
	@test -n "$(SRC)" || { echo "error: SRC=<dir with <source>/<feed>/<file>> is required"; exit 1; }
	$(UV) run python -m ingestion --profile $(PROFILE) --land $(SRC)

bronze-tracer-land: resolve ## Land the committed payer_b members sample (no-op if already landed); prints its gs:// URI
	@sha=$$(sha256sum $(TRACER_SAMPLE) | cut -d' ' -f1); \
	uri="gs://$(PROJECT_ID)-landing/source=payer_b/feed=members/ingest_date=$$(date -u +%F)/sha256=$$sha/$$(basename $(TRACER_SAMPLE))"; \
	existing=$$(gcloud storage ls "gs://$(PROJECT_ID)-landing/source=payer_b/feed=members/**" 2>/dev/null | grep "/sha256=$$sha/" | head -1); \
	if [ -n "$$existing" ]; then echo "$$existing"; else gcloud storage cp --if-generation-match=0 $(TRACER_SAMPLE) "$$uri" >&2 && echo "$$uri"; fi

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

run-stub: resolve ## AD-24 run-identity stub against live BigQuery ops.run_lock (optional)
	uv run python -m pipeline.runner

tf-validate: ## Terraform fmt + validate (no cloud credentials needed)
	terraform fmt -check -recursive
	TF_DATA_DIR=.terraform-validate terraform -chdir=infra/environments/demo init -backend=false -input=false > /dev/null
	TF_DATA_DIR=.terraform-validate terraform -chdir=infra/environments/demo validate

TF_DIR := infra/environments/demo
# Identities stay out of git: impersonators default to the active gcloud account.
TF_VAR_impersonators ?= ["user:$(shell gcloud config get account 2>/dev/null)"]
export TF_VAR_impersonators
PROJECT_ID = $(shell uv run python -c "import yaml;print(yaml.safe_load(open('config/resolved.yaml'))['project_id'])")
DEPLOY_SA = deploy-sa@$(PROJECT_ID).iam.gserviceaccount.com

apply: resolve ## Apply as the owner (first apply, and after teardown recreates the deploy SA)
	terraform -chdir=$(TF_DIR) init -input=false
	terraform -chdir=$(TF_DIR) apply -auto-approve -input=false

tf-bootstrap: apply ## Alias of apply (first apply as the owner); later applies may use tf-apply

teardown: resolve ## Destroy everything Terraform manages; the out-of-band state bucket survives
	terraform -chdir=$(TF_DIR) init -input=false
	terraform -chdir=$(TF_DIR) destroy -auto-approve -input=false
	gcloud storage ls gs://$(PROJECT_ID)-tfstate > /dev/null && echo "state bucket gs://$(PROJECT_ID)-tfstate intact"

budget: resolve ## AD-16: USD budget with alert thresholds on the profile's billing account (owner creds)
	bash tools/budget.sh

tf-plan: ## Terraform plan impersonating the deploy SA
	GOOGLE_IMPERSONATE_SERVICE_ACCOUNT=$(DEPLOY_SA) terraform -chdir=$(TF_DIR) plan -input=false

tf-apply: ## Terraform apply -auto-approve impersonating the deploy SA
	GOOGLE_IMPERSONATE_SERVICE_ACCOUNT=$(DEPLOY_SA) terraform -chdir=$(TF_DIR) apply -auto-approve -input=false

tflint: ## TFLint over infra/ (skipped if tflint is not installed)
	@if command -v tflint > /dev/null 2>&1; then \
		cd infra && tflint --init > /dev/null && tflint --recursive --format compact; \
	else \
		echo "tflint not installed; skipping"; \
	fi

validate: lint test validate-config lint-bytes-cap check-resolved phi-scan marker-check repo-weight edi-preparse-check tf-validate tflint ## Run all local checks (later entries append targets here)

.PHONY: reconcile-storage edi-preparse-check bronze land bronze-tracer-land samples repo-weight generate generate-upload run-stub help upgrade apply teardown budget lint-bytes-cap tf-bootstrap tf-plan tf-apply phi-scan marker-check resolve validate-config check-resolved lint test tf-validate tflint validate
