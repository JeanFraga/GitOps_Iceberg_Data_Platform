---
title: 'Step the Google providers 5 to 8.6.0'
type: 'chore'
ticket: '2'
created: '2026-10-07'
status: 'built'
baseline_revision: '8ad22877ae729ca43e488f66debc432b1409e8db'
route: 'oneshot'
route_source: 'auto'
risk: 'high'
review: 'quick'
review_source: 'pinned'
lenses_ran: [quick]
review_loop_iteration: 0
followup_review_recommended: false
context: []
warnings: []
deferred: []
---

<intent-contract>

## Intent

**Problem:** infra/environments/demo pins google and google-beta `~> 5.0`; the stack targets 8.6.0 and AD-20 requires a committed multi-platform lockfile.

**Approach:** Step the providers 5 -> 6 -> 7 -> 8.6.0 (exact pin at the end), running `terraform init -upgrade` and `terraform plan` from the CLI at each step and recording the output here; generate a linux_amd64/darwin_arm64/linux_arm64 lockfile and stop ignoring it in .gitignore so it is committed.

</intent-contract>

## Tasks & Acceptance

**Acceptance Criteria:**
- Given 8.6.0, when `terraform plan` runs in infra/environments/demo, then it reports no changes.
- Given the committed lockfile, when `terraform providers lock -platform=linux_amd64 -platform=darwin_arm64 -platform=linux_arm64` runs, then the lockfile is unchanged.

## Implementation Notes

Oneshot: two version strings, one .gitignore line, a generated lockfile. Steps were executed before this plan file was written (ordering slip; content unaffected).

Plan output per step (resources: `google_bigquery_dataset.ops` only):

- `~> 6.0` -> installed google/google-beta v6.50.0; plan: "No changes. Your infrastructure matches the configuration."
- `~> 7.0` -> installed v7.46.1; plan: "No changes."
- `8.6.0` -> installed v8.6.0; plan: "No changes."

Files: `infra/environments/demo/main.tf` (pins 8.6.0), `infra/environments/demo/.terraform.lock.hcl` (new, 3 platforms), `.gitignore` (drop lockfile ignore).

## Plan Change Log

## Review Triage Log

### 2026-10-07 — Review pass
- verdicts: 0 findings — high 0, medium 0, low 0, false 0, maybe-false 0

## Verification

**Commands:**
- `terraform -chdir=infra/environments/demo plan -detailed-exitcode` -- expected: exit 0
- `terraform -chdir=infra/environments/demo providers lock -platform=linux_amd64 -platform=darwin_arm64 -platform=linux_arm64 && git diff --exit-code infra/environments/demo/.terraform.lock.hcl` -- expected: no diff
- `make tf-validate` -- expected: pass

## Auto Run Result

- Summary: google/google-beta stepped 5 -> 6.50.0 -> 7.46.1 -> 8.6.0 with a no-change plan at each step; multi-platform lockfile committed.
- Files: infra/environments/demo/main.tf (pin 8.6.0); infra/environments/demo/.terraform.lock.hcl (new); .gitignore (lockfile no longer ignored).
- Review: 0 findings; no patches, no deferrals.
- Follow-up review recommended: false.
- Verification: plan -detailed-exitcode = 0 at 8.6.0; providers lock re-run twice, lockfile byte-identical; make tf-validate pass.
- Residual risks: none known.
