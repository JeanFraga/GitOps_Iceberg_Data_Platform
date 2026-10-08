#!/usr/bin/env bash
# AD-16: create the project budget (alerts only) on the profile's billing account.
# Idempotent by display name. Runs with the owner's gcloud credentials; no SA gets a billing role.
set -euo pipefail
cfg() { uv run python -c "import yaml,sys;c=yaml.safe_load(open('config/resolved.yaml'));print(eval(sys.argv[1]))" "$1"; }
account="$(cfg "c['billing_account']")"
project="$(cfg "c['project_id']")"
amount="$(cfg "c['budget']['amount_usd']")"
name="${project}-budget"
if gcloud billing budgets list --billing-account="$account" --format='value(displayName)' | grep -qx "$name"; then
  echo "budget $name already exists on $account"
  exit 0
fi
rules=()
for t in $(cfg "' '.join(map(str, c['budget']['alert_thresholds']))"); do
  rules+=("--threshold-rule=percent=$t")
done
gcloud billing budgets create --billing-account="$account" --display-name="$name" \
  --budget-amount="${amount}USD" "${rules[@]}" --filter-projects="projects/$project" --quiet
echo "created budget $name on $account"
