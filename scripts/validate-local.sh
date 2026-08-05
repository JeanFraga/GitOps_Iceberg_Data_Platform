#!/usr/bin/env bash
# Reproduces the Terraform CI/CD workflow locally against .env.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

if [[ ! -f .env ]]; then
  echo "Missing .env. Copy .env.example to .env and fill it in." >&2
  exit 1
fi

set -a
# shellcheck disable=SC1091
source .env
set +a

: "${TF_VAR_project_id:?TF_VAR_project_id is empty - this is what breaks the workflow}"

if [[ ! -f "$GOOGLE_APPLICATION_CREDENTIALS" ]]; then
  echo "Missing key file: $GOOGLE_APPLICATION_CREDENTIALS" >&2
  echo "Create it with: gcloud iam service-accounts keys create $GOOGLE_APPLICATION_CREDENTIALS \\" >&2
  echo "  --iam-account=$TF_VAR_pipeline_service_account" >&2
  exit 1
fi

# Resolve to absolute so terraform/gcloud find it regardless of working directory.
export GOOGLE_APPLICATION_CREDENTIALS
GOOGLE_APPLICATION_CREDENTIALS="$(realpath "$GOOGLE_APPLICATION_CREDENTIALS")"

echo "==> Authenticating as $TF_VAR_pipeline_service_account"
gcloud auth activate-service-account \
  --key-file="$GOOGLE_APPLICATION_CREDENTIALS" \
  --project="$GCP_PROJECT_ID"

echo "==> terraform fmt"
terraform fmt -check -recursive

cd infra/environments/dev

echo "==> terraform init"
terraform init -input=false

echo "==> terraform validate"
terraform validate

echo "==> terraform plan"
# pipefail (set above) ensures a failing plan is not masked by tee.
terraform plan -var-file=dev.tfvars -out=tfplan -no-color 2>&1 | tee plan.txt

echo "==> Plan succeeded. Review plan.txt before applying."
