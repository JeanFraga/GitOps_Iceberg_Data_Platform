---
title: 'Refactor sweep'
type: 'refactor'
ticket: '12'
created: '2026-10-08'
status: 'built'
baseline_revision: '15aeb684564a5e240dd1b612fbedc9e24adba8c7'
route: 'oneshot'
route_source: 'auto'
risk: 'low'
review: 'none'
review_source: 'auto'
lenses_ran: []
review_loop_iteration: 0
followup_review_recommended: false
context: []
warnings: []
deferred: []
---

<intent-contract>

## Intent

**Problem:** Ticket plans in epic-platform-baseline carry deferred findings.

**Approach:** Clean up only those deferred findings; leave `make validate` passing and `terraform plan` clean.

</intent-contract>

## Implementation Notes

Oneshot. Disposition of each deferred finding:
- 1.1 `.github/dependabot.yml` targets removed paths: already resolved, because the file was deleted in c277e9d (drop Dependabot). No change.
- 1.4 X12 fingerprint uses distinct segment ids: no code change. First-occurrence distinct ids are an ordered layout that stays stable when the number of repeated loops varies; changing it would move the golden vectors and every era fingerprint. The architecture doc's AD-22 wording should be clarified instead. Left for the user.
- 1.11 Terraform 1.16.5 adopted early: a process note with no code to clean. No change.
- 1.10 BigQueryBackend has no unit test: added `test_bigquery_backend_caps_bytes_and_passes_params`, which checks the bytes cap, the ISO-timestamp parameter containing colons, the MERGE target and the deterministic SELECT.
- 1.5 devcontainer build never run: cannot be checked here because Docker is not available. Left for the user.

## Auto Run Result

- **Files:** `pipeline/test_runner.py` (new BigQuery backend test).
- **Review:** none. The change is a single unit test.
- **Verification:** `make validate` passes (58 tests). `terraform plan -detailed-exitcode` in infra/environments/demo (with `TF_VAR_impersonators` set, as the Makefile does) exits 0 with no changes.
- **Open for the user:** clarify the AD-22 X12 wording; build the devcontainer once Docker is available.
