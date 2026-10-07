---
type: epic
title: "Raw Data Vault including coverage, provider and pharmacy"
parent: initiative-healthcare-dv-platform-upgrade
covers: [CAP-6, CAP-7]
after: []
assignee: ""
risk: medium
---

# Raw Data Vault including coverage, provider and pharmacy

## Description

dbt Fusion builds every Raw Vault hub, link and satellite from the canonical Silver tables with in-house hash, hub, link and satellite macros, including the coverage, provider and pharmacy structures. The build is insert-only and idempotent, handles late records, and uses the shared hash specification so the golden vectors match in Spark, dbt and Python. The MPI, Business Vault and Gold all build on it, and the first-demo tracer ends here (`HUB_CLAIM` and `SAT_CLAIM_VERSION` from one Payer A 837P sample). The intent is CAP-6 and CAP-7 in the initiative spec; the requirement lines are FR-13 to FR-15 and FR-31 to FR-33 in the requirements catalog. This epic is accountable for CAP-7; E8 delivers the FR-31 Gold continuous-enrollment check.

## Outcome

Downstream builders (MPI, Business Vault and Gold) get a Raw Vault that is insert-only, idempotent and hash-consistent across engines; SM-8 (Raw Vault builds under Fusion strict) and the golden vectors show it worked.

## Requirements

Requirements are completed at inception; source is the initiative spec's CAP ids in covers.

## Done when

1. Golden vectors are identical in Spark, dbt and Python, and the same raw ID from two payers gives two different hub keys.
2. An identical reload adds 0 rows, a changed attribute adds exactly 1 satellite row, and late records are correct without reprocessing; replacements and voids share the claim hk, and SSN appears only in `SAT_MEMBER_SENSITIVE`.
3. Coverage spans from ordered 834 transactions match ground truth exactly; an invalid NPI is not hubbed and is counted in drift; pharmacy vault counts equal generator counts per source and month.
4. Hub uniqueness and link referential-integrity tests pass, and the full Raw Vault builds under Fusion strict static analysis with column-level lineage (SM-8).
5. Runs against the demo client project from the CLI (`make <target>` with the demo profile), with output in the demo project's GCP datasets, and passes inside `make e2e-chain` at CI volume on the samples with the epics downstream still passing.

## Boundaries

Follows the capability boundary: the `dbt/` macros (`dv_hash`, `build_hub`, `build_link`, `build_sat`), the staging and raw_vault model folders, and the hub and link tests; sole writer of the `raw_vault` tables under AD-2. It sets its own bytes cap under E1's lint. Not in scope: `HUB_PERSON` and MPI tables (E6, AD-13); Business Vault, PIT, Gold and the FR-31 Gold continuous-enrollment check (E8); `hashing.yaml`, `business_keys.yaml` and the config loader (E1); Silver tables (E4). PHI hardening is out of scope (see the spec's Non-goals).

## References

- parent — /workspaces/GitOps_Iceberg_Data_Platform/_bmad-output/initiative-healthcare-dv-platform-upgrade/initiative-healthcare-dv-platform-upgrade.md
- spec — /workspaces/GitOps_Iceberg_Data_Platform/_bmad-output/initiative-healthcare-dv-platform-upgrade/spec-healthcare-dv-platform-upgrade/spec-healthcare-dv-platform-upgrade.md, Capabilities (CAP-6, CAP-7)
- spec — /workspaces/GitOps_Iceberg_Data_Platform/_bmad-output/initiative-healthcare-dv-platform-upgrade/spec-healthcare-dv-platform-upgrade/requirements-catalog.md, CAP-6 (FR-13..FR-15), CAP-7 (FR-31..FR-33), NFR-7, SM-8
- constraint — /workspaces/GitOps_Iceberg_Data_Platform/_bmad-output/initiative-healthcare-dv-platform-upgrade/architecture-healthcare-dv-platform-upgrade/architecture-healthcare-dv-platform-upgrade.md, AD-1
- constraint — /workspaces/GitOps_Iceberg_Data_Platform/_bmad-output/initiative-healthcare-dv-platform-upgrade/architecture-healthcare-dv-platform-upgrade/architecture-healthcare-dv-platform-upgrade.md, AD-2
- constraint — /workspaces/GitOps_Iceberg_Data_Platform/_bmad-output/initiative-healthcare-dv-platform-upgrade/architecture-healthcare-dv-platform-upgrade/architecture-healthcare-dv-platform-upgrade.md, AD-6
- constraint — /workspaces/GitOps_Iceberg_Data_Platform/_bmad-output/initiative-healthcare-dv-platform-upgrade/architecture-healthcare-dv-platform-upgrade/architecture-healthcare-dv-platform-upgrade.md, AD-7
- constraint — /workspaces/GitOps_Iceberg_Data_Platform/_bmad-output/initiative-healthcare-dv-platform-upgrade/architecture-healthcare-dv-platform-upgrade/architecture-healthcare-dv-platform-upgrade.md, AD-11
- constraint — /workspaces/GitOps_Iceberg_Data_Platform/_bmad-output/initiative-healthcare-dv-platform-upgrade/architecture-healthcare-dv-platform-upgrade/architecture-healthcare-dv-platform-upgrade.md, AD-16
- constraint — /workspaces/GitOps_Iceberg_Data_Platform/_bmad-output/initiative-healthcare-dv-platform-upgrade/architecture-healthcare-dv-platform-upgrade/architecture-healthcare-dv-platform-upgrade.md, AD-24
- input — /workspaces/GitOps_Iceberg_Data_Platform/_bmad-output/initiative-healthcare-dv-platform-upgrade/tickets.toml, [[epic]] id 5 (needs from E1, E2, E4)

## Notes

- Waits on epic-platform-baseline because: it needs `hashing.yaml`, `business_keys.yaml`, the naming standards, the Fusion smoke-gate result and the bytes-cap lint (story-level needs in tickets.toml, not a whole-epic gate).
- Waits on epic-synthetic-data because: coverage, pharmacy and tracer checks compare against ground truth, manifest counts and the samples (story-level needs, not a whole-epic gate).
- Waits on epic-silver-normalization because: every hub, link and satellite stages from the `silver.*` tables (story-level needs, not a whole-epic gate).
- Decision: 2026-10-07 — user accepted the recommended split; E5 stays one epic owning CAP-6 and CAP-7 together (accountable for CAP-7, with E8 delivering the FR-31 Gold part), with no whole-epic gate (only E3 carries one, on the E1 Bronze smoke).
- Source conflict: CAP-6 hub list — the catalog omits `HUB_PERSON` (MPI-owned under AD-13) and lists `HUB_COVERAGE` and `HUB_PROVIDER` under both CAP-6 and CAP-7; merging both in E5 resolves the overlap, and the catalog text should be fixed.
- Unknown: the Fusion smoke-gate outcome (OQ 5, recorded in E1); a failure there reshapes this epic.
- Assumption: an optional, time-boxed AutomateDV spike runs only after the in-house macros pass (FR-15); its diffs are documented, not required to be zero.
- Parked: deferred PHI hardening under AD-14 (tokenization, restricted dataset, de-identification views, policy tags, audit logs); all data is synthetic.
