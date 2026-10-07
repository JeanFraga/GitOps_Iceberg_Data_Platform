---
type: epic
title: "GitHub Actions CD milestone"
parent: initiative-healthcare-dv-platform-upgrade
covers: [CAP-15]
after: []
assignee: ""
risk: medium
---

# GitHub Actions CD milestone

## Description

`pr-validate.yml`, `deploy-main.yml` and `scheduled-e2e.yml` wrap the existing Makefile targets and run over Workload Identity Federation with no logic in Actions: a PR validates and posts a plan without deploying, and a push to `main` deploys only the changed components, serialized per environment. The CLI stays the inner loop. This epic owns the WIF pool and the deploy SA. The intent is CAP-15 in the initiative spec; the requirement lines are FR-39, NFR-9, NFR-10, SM-6 and SM-10 in the requirements catalog.

## Outcome

The platform owner gets merges that are gated and deploys that are automatic and keyless; one green PR run and one green main deploy recorded, with NFR-10 and SM-10 measured, shows it worked.

## Requirements

Requirements are completed at inception; source is the initiative spec's CAP ids in covers.

## Done when

1. A PR run posts the Terraform plan and a failing check blocks merge; one green PR run is recorded.
2. Deploys from `main` are path-filtered and serialized, a failed step stops later steps, and a CLI apply is blocked by the state lock while `deploy-main` runs; one green main deploy is recorded.
3. No JSON keys exist; the deploy SA authenticates over WIF and passes the IAM and bucket-policy review (NFR-9).
4. The median push-to-deploy time is under 15 minutes (NFR-10, SM-10).
5. `scheduled-e2e` runs `make e2e-local` on schedule so SM-6 starts accruing, and the FR-35 PHI scan is clean over the Actions logs.

## Boundaries

Follows the delivery boundary: `.github/workflows/`, the WIF pool and the deploy SA. Not in scope: any pipeline or build logic (it stays in Makefile targets owned by E1 to E11; no logic lives in Actions), the runtime and dashboard SAs (E1), the runner and `make e2e-local` (E10), the dashboard container (E9). See the spec's non-goals.

## References

- parent — /workspaces/GitOps_Iceberg_Data_Platform/_bmad-output/initiative-healthcare-dv-platform-upgrade/initiative-healthcare-dv-platform-upgrade.md
- spec — /workspaces/GitOps_Iceberg_Data_Platform/_bmad-output/initiative-healthcare-dv-platform-upgrade/spec-healthcare-dv-platform-upgrade/spec-healthcare-dv-platform-upgrade.md, Capabilities (CAP-15)
- spec — /workspaces/GitOps_Iceberg_Data_Platform/_bmad-output/initiative-healthcare-dv-platform-upgrade/spec-healthcare-dv-platform-upgrade/requirements-catalog.md, CAP-15 (FR-39), FR-35, NFR-9, NFR-10, SM-6, SM-10
- constraint — /workspaces/GitOps_Iceberg_Data_Platform/_bmad-output/initiative-healthcare-dv-platform-upgrade/architecture-healthcare-dv-platform-upgrade/architecture-healthcare-dv-platform-upgrade.md, AD-18
- constraint — /workspaces/GitOps_Iceberg_Data_Platform/_bmad-output/initiative-healthcare-dv-platform-upgrade/architecture-healthcare-dv-platform-upgrade/architecture-healthcare-dv-platform-upgrade.md, AD-19
- constraint — /workspaces/GitOps_Iceberg_Data_Platform/_bmad-output/initiative-healthcare-dv-platform-upgrade/architecture-healthcare-dv-platform-upgrade/architecture-healthcare-dv-platform-upgrade.md, AD-20
- input — /workspaces/GitOps_Iceberg_Data_Platform/_bmad-output/initiative-healthcare-dv-platform-upgrade/tickets.toml, [[epic]] id 12 (needs from E1, E9, E10)

## Notes

- Waits on epic-platform-baseline because: deploys use E1's state bucket, project and SA pattern, and wrap E1's Makefile targets (story-level need, not a whole-epic gate).
- Waits on epic-consumption because: `deploy-main` builds and deploys E9's dashboard container.
- Waits on epic-orchestration because: `scheduled-e2e` runs E10's `make e2e-local` from the DAG spec.
- Decision: 2026-10-07 — user accepted the recommended split; E1 stays whole, so the FR-39 Actions wiring is E12's while E1 keeps the local lint, test and validate-config targets.
- Parked: SM-3 (billing export under USD 5) is measured after E12 lands; it is tracked on E1.
- Parked: deferred PHI hardening (AD-14, Future Enhancements), including audit logs and identified extracts; all data is synthetic.
- Open question: the project tests GitHub Actions only marginally (CLI-first iteration), so WIF and serialized path-filtered deploy failures may surface late.
