---
type: epic
title: "Business Vault and Gold"
parent: initiative-healthcare-dv-platform-upgrade
covers: [CAP-10]
after: []
assignee: ""
risk: medium
---

# Business Vault and Gold

## Description

dbt Fusion builds the Business Vault derivations (computed claim attributes from claim versions and the 835, the derived visit-claim link, and PIT tables over the golden person key) and every Gold dimension, fact and the OBT on top of the Raw Vault and MPI. Failing tests block Gold. This is the analytical layer the dashboard, extracts and the orchestrated end-to-end run read from. The intent is CAP-10 in the initiative spec; the requirement lines are FR-22 to FR-24 in the requirements catalog. This epic also delivers the FR-31 Gold continuous-enrollment check, for which E5 stays accountable under CAP-7.

## Outcome

Consumers of Gold (the dashboard, extract stubs and the e2e run) get claim counts that net out replacements and voids, one patient row per golden person and cost-bounded as-of queries; SM-8 (Business Vault and Gold build under Fusion strict) and the FR-22 to FR-24 acceptance tests show it worked.

## Requirements

Requirements are completed at inception; source is the initiative spec's CAP ids in covers.

## Done when

1. Claim-version rules are tested: original + replacement + void contributes 0 to `FCT_CLAIMS_MONTHLY`, original + replacement contributes 1; a one-month PIT as-of query reads only its partition and at most 20% of the bytes of a full satellite-join scan.
2. A two-payer person is one `DIM_PATIENT` row keyed on `golden_person_hk`; NDC 10-to-11 (5-4-2) normalization is tested for all 10-digit forms; `FCT_CLAIMS_MONTHLY` and the OBT have the specified partitioning and clustering; the FR-31 continuous-enrollment check with a configurable gap passes.
3. A failing test blocks Gold; Business Vault and Gold build under Fusion strict static analysis with column-level lineage (SM-8); a lineage test on sampled rows traces Gold back to source, file, ingestion time and run ID (NFR-3).
4. Runs against the demo client project from the CLI (`make <target>` with the demo profile), with output in the demo project's GCP datasets, and passes inside `make e2e-chain` at CI volume on the samples with the epics downstream still passing.

## Boundaries

Follows the capability boundary: the `dbt/` business_vault and gold model folders and their tests; sole writer of the `business_vault` and `gold` tables under AD-2. It sets its own bytes cap under E1's lint. Not in scope: Raw Vault hubs, links, satellites and macros (E5); `HUB_PERSON` and MPI tables (E6, AD-13); the dashboard and extracts (E9); late-file partial rebuild orchestration (E10). The Gold block on data drift is parked behind D-7. PHI hardening is out of scope (see the spec's Non-goals).

## References

- parent — /workspaces/GitOps_Iceberg_Data_Platform/_bmad-output/initiative-healthcare-dv-platform-upgrade/initiative-healthcare-dv-platform-upgrade.md
- spec — /workspaces/GitOps_Iceberg_Data_Platform/_bmad-output/initiative-healthcare-dv-platform-upgrade/spec-healthcare-dv-platform-upgrade/spec-healthcare-dv-platform-upgrade.md, Capabilities (CAP-10)
- spec — /workspaces/GitOps_Iceberg_Data_Platform/_bmad-output/initiative-healthcare-dv-platform-upgrade/spec-healthcare-dv-platform-upgrade/requirements-catalog.md, CAP-10 (FR-22..FR-24), CAP-7 (FR-31 Gold check), NFR-3, NFR-7, SM-8
- constraint — /workspaces/GitOps_Iceberg_Data_Platform/_bmad-output/initiative-healthcare-dv-platform-upgrade/architecture-healthcare-dv-platform-upgrade/architecture-healthcare-dv-platform-upgrade.md, AD-1
- constraint — /workspaces/GitOps_Iceberg_Data_Platform/_bmad-output/initiative-healthcare-dv-platform-upgrade/architecture-healthcare-dv-platform-upgrade/architecture-healthcare-dv-platform-upgrade.md, AD-2
- constraint — /workspaces/GitOps_Iceberg_Data_Platform/_bmad-output/initiative-healthcare-dv-platform-upgrade/architecture-healthcare-dv-platform-upgrade/architecture-healthcare-dv-platform-upgrade.md, AD-6
- constraint — /workspaces/GitOps_Iceberg_Data_Platform/_bmad-output/initiative-healthcare-dv-platform-upgrade/architecture-healthcare-dv-platform-upgrade/architecture-healthcare-dv-platform-upgrade.md, AD-9
- constraint — /workspaces/GitOps_Iceberg_Data_Platform/_bmad-output/initiative-healthcare-dv-platform-upgrade/architecture-healthcare-dv-platform-upgrade/architecture-healthcare-dv-platform-upgrade.md, AD-11
- constraint — /workspaces/GitOps_Iceberg_Data_Platform/_bmad-output/initiative-healthcare-dv-platform-upgrade/architecture-healthcare-dv-platform-upgrade/architecture-healthcare-dv-platform-upgrade.md, AD-13
- constraint — /workspaces/GitOps_Iceberg_Data_Platform/_bmad-output/initiative-healthcare-dv-platform-upgrade/architecture-healthcare-dv-platform-upgrade/architecture-healthcare-dv-platform-upgrade.md, AD-16
- constraint — /workspaces/GitOps_Iceberg_Data_Platform/_bmad-output/initiative-healthcare-dv-platform-upgrade/architecture-healthcare-dv-platform-upgrade/architecture-healthcare-dv-platform-upgrade.md, AD-24
- input — /workspaces/GitOps_Iceberg_Data_Platform/_bmad-output/initiative-healthcare-dv-platform-upgrade/tickets.toml, [[epic]] id 8 (needs from E1, E5, E6)

## Notes

- Waits on epic-platform-baseline because: it needs the bytes-cap lint (story-level need in tickets.toml, not a whole-epic gate).
- Waits on epic-raw-vault because: every Business Vault and Gold model reads the Raw Vault hubs, links and satellites (story-level need, not a whole-epic gate).
- Waits on epic-mpi because: PIT, `DIM_PATIENT` and golden-key clustering need the golden person key, built only for `mpi_complete` runs; there is no fallback key (story-level need, not a whole-epic gate).
- Decision: 2026-10-07 — user accepted the recommended split; E8 (Business Vault and Gold) and E9 (consumption) stay separate epics, with no whole-epic gate on E8 (only E3 carries one, on the E1 Bronze smoke).
- Decision: 2026-10-07 — user accepted that E5 stays accountable for CAP-7 while E8 delivers the FR-31 Gold continuous-enrollment check.
- Unknown: the Fusion smoke-gate outcome (OQ 5, recorded in E1); a failure there reshapes this epic.
- Parked: the Gold block on data drift (FR-36), a follow-up story waiting on D-7 (default "unset, report only").
- Parked: deferred PHI hardening under AD-14 (tokenization, restricted dataset, de-identification views, policy tags, audit logs); all data is synthetic.
