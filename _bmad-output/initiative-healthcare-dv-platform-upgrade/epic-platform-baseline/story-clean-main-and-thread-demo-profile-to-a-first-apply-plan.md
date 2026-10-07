---
title: 'Clean main and thread demo profile to a first apply'
type: 'chore'
ticket: '1'
created: '2026-10-07'
status: 'done'
baseline_revision: '73522b819124f42bc64aeddd6a00ea01243a42d3'
route: 'full'
route_source: 'auto'
risk: 'high'
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

**Problem:** Main still carries the v1 taxi platform (Spark jobs, dbt, Looker, Composer, Argo CD gitops, old workflows and modules) and Terraform hardcodes `us-east1`, so nothing on main reflects the new config-driven platform.

**Approach:** Remove the v1 tree from main (it is preserved on branch `v1`), confirm the v1 GCP resources are gone while the state bucket stays, then wire the thinnest config path: `config/profiles/demo.yaml` -> `config/load.py` (`make resolve`) -> `config/resolved.yaml` -> `infra/environments/demo` (yamldecode) -> CLI apply of the `ops` dataset only.

## Boundaries & Constraints

**Always:** Region and project come only from `config/resolved.yaml`; `grep -rn us-east1 infra/` prints nothing. Demo env pins Terraform `= 1.15.8` and google/google-beta `~> 5.0`. Deep-merge logic lives only in `config/load.py` (defaults then profile). `resolved.yaml` is committed and generated, never hand-edited. Apply runs from the CLI with `terraform apply -auto-approve`. State bucket `gitops-iceberg-data-platform-tfstate` is kept; demo uses backend prefix `terraform/demo`.

**Never:** No tables in `ops` (entry 7). No JSON Schema validation, `_template` profile or `validate-config` (entry 3). No uv project, `versions.yaml` or devcontainer rework beyond un-breaking the build (entry 5). No provider step (entry 2), no lockfile commit policy change (entry 2). Do not delete `dependabot.yml` (entry 11). Do not touch the state bucket or the old `terraform/dev` state object.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| HAPPY_PATH | `make resolve` with default profile demo | writes `config/resolved.yaml` = defaults deep-merged with demo profile, deterministic key order | No error expected |
| PROFILE_OVERRIDE | `make resolve PROFILE=x` with no `config/profiles/x.yaml` | no file written | exits nonzero naming the missing profile |
| NESTED_MERGE | defaults `{flags: {a: false, b: true}}`, profile `{flags: {a: true}}` | `{flags: {a: true, b: true}}` | No error expected |

</intent-contract>

## Code Map

- `src/{composer,dbt_project,looker_project,spark_jobs}`, `gitops/`, `infra/modules/{looker,composer,bq_iceberg}`, `.github/workflows/{composer-sync,release,terraform}.yml` -- `git rm -r`; preserved on `origin/v1` (a5f3931).
- `scripts/validate-local.sh` -- reproduces the removed terraform workflow against `infra/environments/dev`; `git rm`.
- `infra/environments/dev/{main.tf,variables.tf,dev.tfvars}` -- `git mv` dir to `infra/environments/demo`, then rewrite: drop variables.tf/dev.tfvars and all module/API blocks; backend bucket stays, prefix -> `terraform/demo`.
- `Makefile` -- `lint`, `test`, `dbt-parse` target src/*; `tf-validate` and `tflint` point at `infra/environments/dev`. Help target via `## ` comments must keep working.
- `.devcontainer/Dockerfile` lines 21-24 COPY `src/*/requirements.txt` (build breaks after removal).
- `.gitignore` -- dbt block points at removed tree; ignores `*.json` and `.terraform.lock.hcl` (leave lockfile line for entry 2).
- `README.md` -- documents the taxi platform throughout.
- GCP project `gitops-iceberg-data-platform` (gcloud has no default project; pass it explicitly). ADC works. Old `terraform/dev/default.tfstate` has zero resources. Google-managed `dataproc-staging-*`/`dataproc-temp-*` buckets exist; they are not Terraform v1 resources.

## Tasks & Acceptance

**Execution:**
- [x] repo -- `git rm -r` the v1 paths in the Code Map plus `scripts/validate-local.sh` -- ticket scope.
- [x] `infra/environments/demo/` -- `git mv infra/environments/dev infra/environments/demo`; `git rm` variables.tf and dev.tfvars; rewrite main.tf: terraform block (`required_version = "1.15.8"`, providers `~> 5.0`, gcs backend prefix `terraform/demo`), `locals { cfg = yamldecode(file("${path.module}/../../../config/resolved.yaml")) }`, both providers from `local.cfg.project_id`/`local.cfg.region`, one `google_bigquery_dataset` `ops` (location `local.cfg.region`, `delete_contents_on_destroy = true`), output the dataset id -- thinnest config-to-Terraform path.
- [x] `config/defaults.yaml`, `config/profiles/demo.yaml` -- defaults hold shared keys (e.g. `flags` with the AD-1 four keys at their defaults); demo holds `profile: demo`, `project_id: gitops-iceberg-data-platform`, `region: us-east1`.
- [x] `config/load.py` -- `resolve(profile) -> dict` (deep-merge defaults + profile) and a CLI `python config/load.py [--profile demo]` writing `config/resolved.yaml` with a "generated, do not edit" header; nonzero exit on missing profile. Entry 3 extends this file.
- [x] `config/test_load.py` -- pytest for the I/O matrix rows.
- [x] `Makefile` -- remove lint/test/dbt-parse; add `resolve` (`PROFILE ?= demo`, runs loader via `uv run --no-project --with pyyaml python config/load.py`); point tf-validate at demo; `validate: resolve tf-validate tflint`.
- [x] `.devcontainer/Dockerfile` -- drop the src requirements COPY/pip lines; keep everything else.
- [x] `.gitignore`, `README.md` -- drop dbt block; README rewritten short: v1 lives on branch `v1`, current layout (config/, infra/environments/demo), `make resolve` + CLI apply.
- [x] GCP -- run v1-gone checks, `make resolve`, `terraform init` + `terraform apply -auto-approve` in demo; record outputs in Implementation Notes.

**Acceptance Criteria:**
- Given main after the change, when running the ticket's `git ls-files ...` list, then it prints nothing, and `git ls-remote --tags --heads origin v1` returns a ref.
- Given the demo project, when running `gcloud composer environments list --locations=us-east1`, `bq ls` and `gcloud storage ls` (project passed explicitly), then no v1 resources appear, and `gcloud storage ls gs://gitops-iceberg-data-platform-tfstate` succeeds.
- Given `make resolve`, when `terraform apply -auto-approve` runs in `infra/environments/demo`, then `bq show --format=json gitops-iceberg-data-platform:ops` reports location `us-east1` and a second `terraform plan` reports no changes.
- Given the repo, when running `grep -rn us-east1 infra/`, then it prints nothing; `make tf-validate` passes.

## Implementation Notes

- v1 tree removed; `origin/v1` at a5f3931 confirmed via `git ls-remote`.
- v1-gone checks (project passed explicitly): Composer us-east1 lists 0 items; `bq ls` empty before apply; `gcloud storage ls` shows only the tfstate bucket and Google-managed `dataproc-staging-*`/`dataproc-temp-*` buckets; tfstate bucket readable.
- `make resolve` -> `config/resolved.yaml` (sorted keys, generated header). `make resolve PROFILE=x` exits nonzero naming the profile.
- `terraform init` + `apply -auto-approve` in demo: 1 added, output `ops_dataset_id = "ops"`; `bq show` location `us-east1`; second plan: no changes.
- AD-1 flag keys used in defaults: workflows_enabled, composer_enabled, dataproc_schedule_enabled (false), ml_fallback_enabled (true).
- Left for entry 11: `.github/dependabot.yml` still references `/src/spark_jobs`, `/src/dbt_project`, `/infra/environments/dev`.
- Stale local `.terraform/` and lockfile from the old dev dir were deleted (untracked) before init.

## Plan Change Log

## Review Triage Log

## Design Notes

AD-1 names `config/clients/` and `config/loader.py`; the ticket (later and more specific, and what entry 3 extends) names `config/profiles/` and `config/load.py` and a single `config/resolved.yaml`. Follow the ticket.

## Verification

**Commands:**
- `uv run --no-project --with pyyaml --with pytest pytest config/` -- expected: pass
- `make resolve && git diff --exit-code config/resolved.yaml` -- expected: no diff after commit
- `make tf-validate` -- expected: pass
- `terraform -chdir=infra/environments/demo plan -detailed-exitcode` -- expected: exit 0 after apply
- `grep -rn us-east1 infra/` -- expected: no output
