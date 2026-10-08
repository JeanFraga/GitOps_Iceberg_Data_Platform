---
title: 'Cost guardrails and teardown'
type: 'feature'
ticket: '8'
created: '2026-10-08'
status: 'in-progress'
baseline_revision: 'e7e9e224f07dcb266c7290580cfbf1f26d3245f1'
route: 'full'
route_source: 'auto'
risk: 'medium'
review: ''
review_source: ''
lenses_ran: []
review_loop_iteration: 0
followup_review_recommended: false
context: []
warnings: []
deferred: []
---

<intent-contract>

## Intent

**Problem:** Nothing caps spend: there is no budget alert, no check that a profile sets a BigQuery bytes-billed cap (AD-16), and no one-command teardown.

**Approach:** Add the billing account and bytes cap to the config contract; a `make budget` target that creates (idempotently) a USD 5 budget with 50/90/100% alerts on the profile's billing account using the owner's gcloud credentials; `make lint-bytes-cap PROFILE=<profile name or yaml path>` that fails when the resolved profile has no cap; and `make teardown` (terraform destroy) plus `make apply` (owner apply). Then run budget, teardown and apply live.

## Boundaries & Constraints

**Always:**
- Config contract: profile key `billing_account` (pattern `^[0-9A-F]{6}-[0-9A-F]{6}-[0-9A-F]{6}$`); `cost.max_bytes_billed` (integer > 0) set in each profile (`demo.yaml`: 10737418240, i.e. 10 GiB; `_template.yaml`: same value, billing account placeholder `000000-000000-000000`); `budget.amount_usd: 5` and `budget.alert_thresholds: [0.5, 0.9, 1.0]` in `defaults.yaml`. Add all to `profile.schema.json`; `billing_account` and `budget` required, `cost` NOT required by the schema (the lint is the gate, so the no-cap fixture still resolves). Regenerate `config/resolved.yaml` with `make resolve`.
- Demo billing account is `016257-CB508D-E7A17B` (the project's linked account).
- `lint-bytes-cap`: a `check-bytes-cap` subcommand in `tools/guardrails.py` (or a function in `config/load.py`, reuse `resolve`/`deep_merge`) that deep-merges `defaults.yaml` with the profile (a profile name under `config/profiles/`, or a path to a yaml file) and exits 1 with a message naming the profile when `cost.max_bytes_billed` is missing or not a positive int. Fixture `config/tests/fixtures/no_cap.yaml` = a full profile without `cost`. Add it to `make validate` for `PROFILE` (default demo). Pytest covers pass (demo) and fail (fixture).
- `make budget`: reads `billing_account`, `project_id` and `budget` from `config/resolved.yaml`; display name `<project_id>-budget`; if `gcloud billing budgets list --billing-account=... --format='value(displayName)'` already lists it, print and exit 0; else `gcloud billing budgets create --billing-account=... --display-name=... --budget-amount=5USD --threshold-rule=percent=0.5 --threshold-rule=percent=0.9 --threshold-rule=percent=1.0 --filter-projects=projects/<project_id> --quiet`. No billing role granted to any SA; no budget in Terraform.
- `make teardown`: `terraform -chdir=$(TF_DIR) destroy -auto-approve -input=false` as the owner (no impersonation, since destroy removes the deploy SA). The state bucket is not in Terraform state (backend only), so it survives; teardown then runs `gcloud storage ls gs://<project_id>-tfstate` to prove it. `make apply` = owner apply (same recipe as `tf-bootstrap`; make `tf-bootstrap` depend on or alias it).
- Help text (`## ...`) on every new target; add to `.PHONY`.

**Never:** No budget-cap enforcement (alerts only, AD-16); no Pub/Sub or notification channels; no change to the state bucket; no new Terraform resources.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| CAP_SET | `PROFILE=demo` | lint exits 0 | No error expected |
| NO_CAP | `PROFILE=config/tests/fixtures/no_cap.yaml` | exits 1, message names the profile and `cost.max_bytes_billed` | non-zero exit |
| BAD_CAP | profile with `cost.max_bytes_billed: 0` | exits 1 | non-zero exit |
| BUDGET_EXISTS | budget with the display name present | `make budget` prints it exists, creates nothing | exit 0 |

</intent-contract>

## Code Map

- `config/load.py` -- `resolve(profile, config_dir)` takes a name; `deep_merge`, `_read`, `validate`, `main`. Reuse for the lint (accept a path when the arg ends in `.yaml`).
- `config/test_load.py` -- existing pytest style for the loader; add lint tests here or beside.
- `config/defaults.yaml`, `config/profiles/{demo,_template}.yaml`, `config/schemas/profile.schema.json` (`additionalProperties: false` at root), `config/resolved.yaml` (generated; `make check-resolved` fails if stale).
- `tools/guardrails.py` -- existing subcommand CLI (phi-scan, marker-check); acceptable home for the lint.
- `Makefile` -- `PROFILE ?= demo`, `TF_DIR`, `TF_VAR_impersonators` export, `tf-bootstrap`, `validate`, `.PHONY`. `PROFILE` is also used by `resolve`.
- `infra/environments/demo/main.tf` -- backend bucket `gitops-iceberg-data-platform-tfstate` (out-of-band).

## Tasks & Acceptance

**Execution:**
- [ ] `config/defaults.yaml`, `config/profiles/demo.yaml`, `config/profiles/_template.yaml`, `config/schemas/profile.schema.json`, `config/resolved.yaml` -- contract keys above.
- [ ] `config/load.py` or `tools/guardrails.py` -- bytes-cap check; `config/tests/fixtures/no_cap.yaml`; tests for the matrix rows CAP_SET, NO_CAP, BAD_CAP.
- [ ] `tools/budget.sh` -- idempotent budget create (matrix BUDGET_EXISTS checked live by running twice).
- [ ] `Makefile` -- `lint-bytes-cap`, `budget`, `teardown`, `apply`; add `lint-bytes-cap` to `validate`.
- [ ] Live: `make budget` (twice), `make teardown`, `make apply`, then `bash infra/modules/bq_ops/check_schemas.sh`.

**Acceptance Criteria:**
- Given the repo, when `make lint-bytes-cap PROFILE=config/tests/fixtures/no_cap.yaml` runs, then it exits nonzero; with `PROFILE=demo` it exits 0.
- Given `make budget` ran, when `gcloud billing budgets list --billing-account=016257-CB508D-E7A17B` runs, then a USD 5 budget for the project shows thresholds 0.5, 0.9 and 1.0.
- Given `make teardown` then `make apply`, when `terraform plan` runs in infra/environments/demo, then it shows no changes and `gs://gitops-iceberg-data-platform-tfstate` still exists.

## Implementation Notes

## Plan Change Log

## Review Triage Log

## Verification

**Commands:**
- `make validate` -- expected: pass (includes lint, tests, check-resolved, lint-bytes-cap).
- `make lint-bytes-cap PROFILE=config/tests/fixtures/no_cap.yaml; echo $?` -- expected: nonzero.
- `make budget && make budget` -- expected: second run reports it exists.
- `gcloud billing budgets list --billing-account=016257-CB508D-E7A17B --format=yaml` -- expected: three thresholds, 5 USD.
- `make teardown && make apply` -- expected: destroy and apply complete; tfstate bucket listed.
- `terraform -chdir=infra/environments/demo plan -detailed-exitcode -input=false` -- expected: exit 0.

## Auto Run Result

- **Implemented (in main session, after the implementer handoff was denied by the auto-mode classifier as "Blind Apply"):** config keys `billing_account`, `budget`, `cost.max_bytes_billed` (schema, defaults, demo and `_template` profiles, resolved.yaml); `config/load.py --check-bytes-cap` accepting a profile name or yaml path; fixture `config/tests/fixtures/no_cap.yaml`; tests for CAP_SET, NO_CAP, BAD_CAP; `tools/budget.sh` (idempotent by display name); Makefile `apply`, `teardown`, `budget`, `lint-bytes-cap` (in `validate`), `tf-bootstrap` now aliases `apply`.
- **Deviation:** existing `test_happy_path_writes_deterministic_resolved` asserted `drift:` was the first key; it now asserts top-level keys are sorted.
- **Verified locally:** `make validate` passes; `make lint-bytes-cap PROFILE=config/tests/fixtures/no_cap.yaml` exits nonzero.
- **Not run (needs the user):** `make budget` (twice, for BUDGET_EXISTS), `make teardown`, `make apply`, clean `terraform plan`, `bash infra/modules/bq_ops/check_schemas.sh`. Review pass not run.
