---
type: epic
title: "Dashboard and extract stubs"
parent: initiative-healthcare-dv-platform-upgrade
covers: [CAP-11]
after: []
assignee: ""
risk: low
---

# Dashboard and extract stubs

## Description

A Streamlit dashboard reads Gold through four tiles (monthly paid, active-coverage members, top diagnoses, cross-payer persons) under a bytes cap, running locally and on authenticated Cloud Run with min instances 0. Two illustrative, synthetic-only extract stubs (a HEDIS-style BCS denominator and an MA encounter-style payer extract) write fixed-schema files. This is the consumption surface on top of the Gold layer. The intent is CAP-11 in the initiative spec; the requirement lines are FR-25 and FR-26 in the requirements catalog.

## Outcome

Reviewers of the demo see Gold answers in an authenticated dashboard and in fixed-schema extract files without touching any layer below Gold; the FR-25 and FR-26 acceptance tests show it worked.

## Requirements

Requirements are completed at inception; source is the initiative spec's CAP ids in covers.

## Done when

1. The 4 tiles read only Gold under the dashboard's bytes cap, and the dashboard SA can read the `gold` dataset only; the same code runs locally.
2. Cloud Run (min instances 0) rejects unauthenticated requests.
3. The BCS and MA extract stubs each write a named file whose fixed schema is tested; both are labeled illustrative and synthetic-only.
4. The dashboard source, container and screenshot are committed, the "synthetic data, no real PHI" label is shown, and the FR-35 scan is clean over the dashboard logs with a canary seeded.
5. Runs against the demo client project from the CLI (`make <target>` with the demo profile), with output in the demo project's GCP datasets, and passes inside `make e2e-chain` at CI volume on the samples with the epics downstream still passing.

## Boundaries

Follows the deployment boundary (Cloud Run is separate from the dbt build): `dashboard/`, `extracts/`, and the Cloud Run Terraform touch point built on E1's module pattern. It sets its own bytes cap under E1's lint and enforces Gold-only reads for the dashboard SA (which E1 creates). Not in scope: Gold models (E8), the dashboard SA itself and the bytes-cap lint (E1), the GitHub Actions deploy of the container (E12). The Phase 2 PBIP layout is room left, not built. PHI hardening and identified extracts are out of scope (see the spec's Non-goals).

## References

- parent — /workspaces/GitOps_Iceberg_Data_Platform/_bmad-output/initiative-healthcare-dv-platform-upgrade/initiative-healthcare-dv-platform-upgrade.md
- spec — /workspaces/GitOps_Iceberg_Data_Platform/_bmad-output/initiative-healthcare-dv-platform-upgrade/spec-healthcare-dv-platform-upgrade/spec-healthcare-dv-platform-upgrade.md, Capabilities (CAP-11)
- spec — /workspaces/GitOps_Iceberg_Data_Platform/_bmad-output/initiative-healthcare-dv-platform-upgrade/spec-healthcare-dv-platform-upgrade/requirements-catalog.md, CAP-11 (FR-25, FR-26), FR-35
- constraint — /workspaces/GitOps_Iceberg_Data_Platform/_bmad-output/initiative-healthcare-dv-platform-upgrade/architecture-healthcare-dv-platform-upgrade/architecture-healthcare-dv-platform-upgrade.md, AD-1
- constraint — /workspaces/GitOps_Iceberg_Data_Platform/_bmad-output/initiative-healthcare-dv-platform-upgrade/architecture-healthcare-dv-platform-upgrade/architecture-healthcare-dv-platform-upgrade.md, AD-14
- constraint — /workspaces/GitOps_Iceberg_Data_Platform/_bmad-output/initiative-healthcare-dv-platform-upgrade/architecture-healthcare-dv-platform-upgrade/architecture-healthcare-dv-platform-upgrade.md, AD-16
- constraint — /workspaces/GitOps_Iceberg_Data_Platform/_bmad-output/initiative-healthcare-dv-platform-upgrade/architecture-healthcare-dv-platform-upgrade/architecture-healthcare-dv-platform-upgrade.md, AD-18
- input — /workspaces/GitOps_Iceberg_Data_Platform/_bmad-output/initiative-healthcare-dv-platform-upgrade/tickets.toml, [[epic]] id 9 (needs from E1, E8)

## Notes

- Waits on epic-platform-baseline because: it needs the dashboard SA, the bytes-cap lint and the Terraform module pattern (story-level need in tickets.toml, not a whole-epic gate).
- Waits on epic-business-vault-gold because: every tile and extract reads the Gold marts (story-level need, not a whole-epic gate).
- Decision: 2026-10-07 — user accepted the recommended split; E8 (Business Vault and Gold) and E9 (consumption) stay separate epics because Cloud Run is a separate deployment boundary, with no whole-epic gate on E8 (only E3 carries one, on the E1 Bronze smoke).
- Parked: deferred PHI hardening under AD-14 (tokenization, restricted dataset, de-identification views, policy tags, audit logs, identified extracts); all data is synthetic.
