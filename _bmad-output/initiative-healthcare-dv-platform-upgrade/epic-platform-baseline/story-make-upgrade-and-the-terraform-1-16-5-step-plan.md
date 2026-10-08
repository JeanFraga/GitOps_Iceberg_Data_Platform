---
title: 'make upgrade and the Terraform 1.16.5 step'
type: 'chore'
ticket: '11'
created: '2026-10-07'
status: done
baseline_revision: '9b405e72752731d8f5f5036ce72d3f5a3cbe9f26'
route: 'oneshot'
route_source: 'auto'
risk: 'medium'
review: 'quick'
review_source: 'pinned'
lenses_ran: [quick]
review_loop_iteration: 0
followup_review_recommended: false
context: []
warnings: []
deferred:
  - summary: >-
      Terraform 1.16.5 taken 5 days after release and without the platform-upgrade skill's Step 3 confirmation.
    evidence: |-
      Skill policy: 7-day wait unless the user asks sooner; confirm bumps before editing. The ticket names 1.16.5 and the
      run was instructed to proceed without input. Owner should confirm the exception or roll back (git revert of this commit).
    location: >-
      .devcontainer/devcontainer.json, infra/**/main.tf
    severity: low
---

<intent-contract>

## Intent

**Problem:** Terraform is pinned at 1.15.8 (stack target 1.16.5), there is no `make upgrade` entry point for the AD-20 manual upgrade, and `.github/dependabot.yml` still exists (AD-20: no Dependabot) and points at removed paths.

**Approach:** Add `make upgrade` that prints the platform-upgrade skill invocation; run the skill's flow scoped to Terraform 1.15.8 -> 1.16.5 (devcontainer feature, `required_version` in demo and modules; versions.yaml holds no Terraform pin since Terraform stays native); delete `dependabot.yml`; validate and plan; one commit.

</intent-contract>

## Implementation Notes

Oneshot: four version strings, one Makefile target, one deletion.

Platform-upgrade skill flow, scoped by the ticket to Terraform:
- Inventory: `required_version` in infra/environments/demo/main.tf (`1.15.8`), infra/modules/{iam,storage}/main.tf (`>= 1.15.8`), .devcontainer/devcontainer.json terraform feature (`1.15.8`). No workflows (removed in 1.1).
- Latest stable: 1.16.5 (releases.hashicorp.com, created 2026-10-02). Policy asks for a 7-day wait; 1.16.5 is 5 days old. Taken anyway because the ticket names 1.16.5 explicitly (the user's ask overrides the wait per the skill).
- Step 3 (user confirmation) skipped: the ticket fixes the scope and the run is unattended by instruction.
- Local binary: downloaded terraform_1.16.5_linux_amd64.zip, SHA256 verified against the release SHA256SUMS, installed over /usr/local/bin/terraform (old binary copied to the session scratch dir). The devcontainer gets 1.16.5 from the feature pin on next rebuild.
- Validate: `make validate` exit 0. `terraform plan` (owner creds): 14 to add, 0 change, 0 destroy -- the pending 1.6 IAM/storage resources; no stateful replacement. Provider lockfile unchanged.
- `dependabot.yml` deleted (also clears the deferred item from 1.1).

## Plan Change Log

## Review Triage Log

### 2026-10-07 — Review pass
- verdicts: 6 findings — high 0, medium 1, low 2, false 3, maybe-false 0
- findings:
  - `[medium]` `[patch]` `make tf-plan` target missing — correct: the 1.6 Makefile edit was in the command the permission classifier denied, so tf-bootstrap/tf-plan/tf-apply never landed. Added in a follow-up commit (initially triaged false in error).
  - `[false]` `[reject]` `make upgrade` only prints, epic says runs end to end — the ticket text defines it as printing the skill invocation (the skill is interactive, run inside Claude Code).
  - `[low]` `[defer]` skill's 7-day wait and confirmation step skipped — user instructed an unattended run and the ticket names 1.16.5; deferred for owner confirmation.
  - `[false]` `[reject]` modules' `>= 1.16.5` floor is tighter than needed — the ticket AC requires `grep 1.15.8 infra/` to print nothing.
  - `[low]` `[reject]` plan output only summarized — the summary (14 add, 0 change, 0 destroy, all pending 1.6 resources) is the reviewed result; attaching raw output adds nothing.
  - `[false]` `[reject]` dependabot deletion appears twice — artifact of how the review diff was assembled; the commit has one deletion.

## Verification

**Commands:**
- `grep -rn '1\.15\.8' .devcontainer infra versions.yaml` -- expected: nothing (local .terraform cache refreshed with `init -reconfigure`)
- `terraform version` -- expected: 1.16.5 (here: installed binary; devcontainer: feature pin, not rebuildable here)
- `make validate` -- expected: exit 0
- `test ! -e .github/dependabot.yml`

## Auto Run Result

- Summary: Terraform pinned to 1.16.5 (devcontainer feature, demo root, modules), `make upgrade` prints the platform-upgrade skill invocation, dependabot.yml deleted.
- Files: .devcontainer/devcontainer.json, infra/environments/demo/main.tf, infra/modules/{iam,storage}/main.tf, Makefile, .github/dependabot.yml (deleted).
- Review: 1 patch (medium, follow-up commit), 1 deferred (release-age / confirmation exception), 5 rejected.
- Follow-up review recommended: false.
- Verification: grep 1.15.8 empty; terraform version 1.16.5 (local binary); make validate exit 0; plan 14 add / 0 change / 0 destroy.
- Residual risks: devcontainer rebuild not exercised here (no Docker).
