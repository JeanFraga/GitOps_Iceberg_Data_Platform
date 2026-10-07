---
name: platform-upgrade
description: Run the manual platform upgrade for this repo — find every pinned version (Terraform, Google providers, dbt Fusion, Dataproc runtime, Iceberg, Python packages, GitHub Actions, devcontainer), check each against its latest stable release, bump pins and lockfiles, validate, and commit one upgrade change set. Use when the user says "run the platform upgrade", "upgrade dependencies", "check for new versions", "bump versions", or invokes /platform-upgrade.
---

# Platform Upgrade

Upgrades are **manual and on demand** (architecture spine AD-20; PRD FR-40). There are no bot PRs and no Dependabot. Each run ends as **one upgrade change set**, or as a report that nothing needs changing. The change set is committed to `main` under the current convention, or opened as one PR if branches are in use.

**Policy:**
- Track the **latest stable** release, but always pin an exact version.
- Never take alpha, beta, rc, canary or nightly builds.
- Wait **7 days** after a release before taking it, unless the user asks for it sooner.
- Skip any release flagged as bad (for example, dbt Fusion 2.0.7).
- Dataproc and dbt Fusion matter most: they are where the performance gains come from.

Authority files to read first:
- `_bmad-output/initiative-healthcare-dv-platform-upgrade/architecture-healthcare-dv-platform-upgrade/architecture-healthcare-dv-platform-upgrade.md`: AD-20 (version policy), AD-21 (Python 3.12 everywhere), and the Stack table.
- `versions.yaml` at the repo root, if it exists. It holds pins that no package registry tracks.

## Step 1: Inventory every pin

Search the repo. Don't rely on memory. Pins live in two kinds of places.

**`versions.yaml`**, the target state for pins with no registry:
- Dataproc runtime
- Composer image
- dbt Fusion
- Iceberg coordinates

**Native files**, which stay native:

| Area | Where to look |
|---|---|
| Terraform CLI | `required_version` in every `*.tf`, `.devcontainer/devcontainer.json`, `.github/workflows/*.yml` (`terraform_version`) |
| Terraform providers | `required_providers` in every root and module (`google` and `google-beta` must be the **same** version), `.terraform.lock.hcl` |
| tflint and its ruleset | `.tflint.hcl`, workflow `tflint_version` |
| Python packages | `pyproject.toml` and `uv.lock` per uv project, plus any leftover `requirements*.txt` |
| dbt | `dbt_project.yml` `require-dbt-version`, `packages.yml`, `package-lock.yml`, and how the Fusion binary gets installed (devcontainer, CI) |
| Spark / Iceberg | `versions.yaml`, job submit scripts, `.github/workflows/*`, test `conftest.py` (the local Spark and Iceberg jars must match the Dataproc runtime) |
| Composer (flagged off) | Composer module `image_version` |
| GitHub Actions | every `uses:` (pin to a commit SHA, with the version as a comment) |
| Devcontainer | `Dockerfile` base image, JDK, uv, features in `devcontainer.json` |

Watch for the same version written by hand in two places. List every duplicate; the fix is to move the value into `versions.yaml` or config.

Output: a table with columns `component | current pin | file:line`.

## Step 2: Find the latest stable version of each component

Check the official sources with web search or fetch. Run independent lookups in parallel (subagents are fine). For each component, record the latest stable version, its release date, the source URL, and any breaking changes since the current pin.

| Component | Official source |
|---|---|
| Terraform | releases.hashicorp.com/terraform |
| google / google-beta | registry.terraform.io/providers/hashicorp/google (read the upgrade guide for each major) |
| Dataproc Serverless runtimes | cloud.google.com/dataproc-serverless/docs/concepts/versions/spark-runtime-versions (GA vs preview, LTS vs non-LTS, end-of-support date, and the Spark, Java, Scala and Python versions it ships) |
| Iceberg | iceberg.apache.org/releases (the runtime jar must match the runtime's Spark and Scala versions) |
| BigLake REST catalog | cloud.google.com/bigquery/docs/blms-rest-catalog (minimum runtime and Iceberg versions) |
| dbt Fusion | docs.getdbt.com/docs/fusion/fusion-releases (the "latest" channel; note known-bad builds) |
| Composer images | cloud.google.com/composer/docs/composer-versions |
| PyPI packages | pypi.org/project/<name> (Splink, XGBoost, DuckDB, Streamlit, ruff, pytest, google-cloud-*, astronomer-cosmos) |
| uv | github.com/astral-sh/uv/releases |
| GitHub Actions | the action's releases page |

**Compatibility rules.** Decide these before bumping anything:
- **Python** stays on 3.12 everywhere (AD-21) unless the Dataproc runtime moves. If the runtime's Python changes, every uv project moves with it in the same upgrade.
- **Spark, Java, Scala and Iceberg** follow the Dataproc runtime. Update the local test jars and JDK in the same upgrade.
- **Provider majors move one step at a time:** 8 to 9, never 8 to 10. A major bump gets its own commit within the same upgrade.
- **Leaving a non-LTS runtime.** If the current Dataproc runtime is within 60 days of end of support, the upgrade is required, not optional.

Output: a table with columns `component | current | latest stable (date) | action: bump/keep/blocked | risk | source`.

## Step 3: Confirm with the user

Show the table from Step 2. Ask which bumps to apply, recommending all safe ones. List any major or breaking bumps separately, with what they break. **Don't edit files before the user confirms.**

## Step 4: Apply

1. Work where the repo convention says. Right now that is directly on an up-to-date `main`, with no feature branch. If the convention changes back to branches, use `chore/platform-upgrade-YYYY-MM-DD`.
2. Update the pins. Native files stay native, and values with no registry go in `versions.yaml`.
3. Regenerate the lockfiles:
   - `uv lock --upgrade` in each uv project
   - `terraform init -upgrade`, then `terraform providers lock -platform=linux_amd64 -platform=darwin_arm64`
   - `dbt deps --upgrade`, if dbt packages exist
4. Fix code that the breaking changes from Step 2 affect. Keep those fixes to the minimum the upgrade needs.
5. If `make upgrade` and `make versions-check` exist, use them for steps 2–3. If they don't exist yet, do the steps by hand and tell the user they're still missing (AD-20).

## Step 5: Validate

Run each check and report its real output. Don't summarize a failure as a pass.
1. `make validate`, or its parts: lint, unit tests, `terraform fmt`, `terraform validate`, tflint, and dbt parse/compile with Fusion.
2. `terraform plan` against dev, run from the CLI (CLI-first). **Block the upgrade if the plan replaces any stateful resource**: buckets, datasets, tables, the Iceberg catalog, service accounts. Show the plan diff to the user.
3. Run the end-to-end pipeline at CI volume with the local runner (`make e2e-local` or its equivalent). Compare these with the last green run:
   - Gold row counts
   - hash-key sets
   - MPI metrics
   - runtime

   Any difference in counts or keys **blocks** the upgrade. Report runtime changes as information.
4. Run the dbt Fusion smoke gate: a full `dbt build` on Fusion. There is no automatic fallback to dbt Core (AD-15). If it fails, stop and report to the user.

Only `terraform plan` and runs at CI volume may touch the cloud during validation. Don't run `apply`, except as Step 6 allows. Keep expensive flags (Composer, Workflows) off.

## Step 6: Commit

- Commit in logical order: one commit for each provider major, then runtime/Spark/Iceberg, then dbt, then Python packages, then Actions and the devcontainer.
- Put the summary in the last commit message (or in the PR body, if branches are in use), titled `chore: platform upgrade YYYY-MM-DD`. It contains:
  - the Step 2 table (before → after, with source links)
  - breaking changes and how each was handled
  - validation results, including the plan summary and e2e comparison numbers
  - the rollback note: revert the commits and re-apply, and Dataproc runtime changes take effect on the next batch.
- Ask the user before pushing or applying. In this repo, applying runs from the devcontainer CLI after the user approves the plan. GitHub Actions deploys after the merge.

## Rollback

`git revert` the upgrade commits, then re-apply from the CLI. The Terraform state bucket has no object versioning (the POC keeps the bucket as-is), so review the provider-major plans carefully before applying. A production client should turn on versioning for that bucket.
