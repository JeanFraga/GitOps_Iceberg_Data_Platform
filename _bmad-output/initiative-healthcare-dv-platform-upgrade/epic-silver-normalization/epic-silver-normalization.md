---
type: epic
title: "Config-driven Silver, drift and quarantine"
parent: initiative-healthcare-dv-platform-upgrade
covers: [CAP-4]
after: []
assignee: ""
risk: medium
---

# Config-driven Silver, drift and quarantine

## Description

Every reconciled Bronze era maps through validated YAML to the 8 canonical Silver tables, so a source or schema era is supported by mapping configuration alone. Cast failures and unmapped eras are quarantined and can be replayed without re-landing, and every manifest drift scenario appears in a per-file drift report. This epic also delivers the FR-36 per-file data-drift profiles and flagging (report-only until D-7 is set). The Raw Vault and every later layer build from these Silver tables. The intent is CAP-4 in the initiative spec; the requirement lines are FR-8 to FR-11 in the requirements catalog, plus the E4 part of FR-36.

## Outcome

Pipeline builders and client onboarding get Silver tables driven by configuration alone, with failing files held in quarantine rather than dropped; CAP-4's signals (SM-2, SM-4, SM-C2) show it worked.

## Requirements

Requirements are completed at inception; source is the initiative spec's CAP ids in covers.

## Done when

1. The mapping validator runs on every PR and rejects a non-canonical target and a missing required column without a default; the schema validator rejects a canonical column without a `phi` tag.
2. An unmapped era is quarantined and reported, then replays through Silver via `make rerun-quarantined` without re-landing once a mapping is added; a column cast-failure rate above the mapping threshold (default 5%) quarantines the file with `CAST_THRESHOLD`, following AD-9 precedence, and a MERGE rerun produces identical counts.
3. The drift report covers 100% of manifest scenarios (SM-4); data drift warns and never blocks while D-7 is unset.
4. The FR-35 scan is clean over quarantine payloads and drift reports, with a canary seeded in the input.
5. Runs against the demo client project from the CLI (`make <target>` with the demo profile), with output in the demo project's GCP datasets, and passes inside `make e2e-chain` at CI volume on the samples with the epics downstream still passing.

## Boundaries

Follows the capability boundary: the Silver normalizer and drift module, `config/mappings/` and `config/schemas/canonical_*`, the `silver.*` tables, `ops.quarantine` and `ops.drift_report` (sole writer under AD-2), the `silver_loaded` lifecycle state and `make rerun-quarantined`. It sets its own bytes cap under E1's lint. Not in scope: `ops.*` DDL, the config loader, reason codes and the D-7 key (E1); landing, Bronze and lifecycle up to `reconciled` (E3); drift samples and manifest (E2); the Gold drift block (parked). PHI hardening is out of scope (see the spec's Non-goals).

## References

- parent — /workspaces/GitOps_Iceberg_Data_Platform/_bmad-output/initiative-healthcare-dv-platform-upgrade/initiative-healthcare-dv-platform-upgrade.md
- spec — /workspaces/GitOps_Iceberg_Data_Platform/_bmad-output/initiative-healthcare-dv-platform-upgrade/spec-healthcare-dv-platform-upgrade/spec-healthcare-dv-platform-upgrade.md, Capabilities (CAP-4)
- spec — /workspaces/GitOps_Iceberg_Data_Platform/_bmad-output/initiative-healthcare-dv-platform-upgrade/spec-healthcare-dv-platform-upgrade/requirements-catalog.md, CAP-4 (FR-8..FR-11), FR-35, FR-36, NFR-5, SM-2, SM-4, SM-C2
- constraint — /workspaces/GitOps_Iceberg_Data_Platform/_bmad-output/initiative-healthcare-dv-platform-upgrade/architecture-healthcare-dv-platform-upgrade/architecture-healthcare-dv-platform-upgrade.md, AD-1
- constraint — /workspaces/GitOps_Iceberg_Data_Platform/_bmad-output/initiative-healthcare-dv-platform-upgrade/architecture-healthcare-dv-platform-upgrade/architecture-healthcare-dv-platform-upgrade.md, AD-2
- constraint — /workspaces/GitOps_Iceberg_Data_Platform/_bmad-output/initiative-healthcare-dv-platform-upgrade/architecture-healthcare-dv-platform-upgrade/architecture-healthcare-dv-platform-upgrade.md, AD-5
- constraint — /workspaces/GitOps_Iceberg_Data_Platform/_bmad-output/initiative-healthcare-dv-platform-upgrade/architecture-healthcare-dv-platform-upgrade/architecture-healthcare-dv-platform-upgrade.md, AD-6
- constraint — /workspaces/GitOps_Iceberg_Data_Platform/_bmad-output/initiative-healthcare-dv-platform-upgrade/architecture-healthcare-dv-platform-upgrade/architecture-healthcare-dv-platform-upgrade.md, AD-8
- constraint — /workspaces/GitOps_Iceberg_Data_Platform/_bmad-output/initiative-healthcare-dv-platform-upgrade/architecture-healthcare-dv-platform-upgrade/architecture-healthcare-dv-platform-upgrade.md, AD-9
- constraint — /workspaces/GitOps_Iceberg_Data_Platform/_bmad-output/initiative-healthcare-dv-platform-upgrade/architecture-healthcare-dv-platform-upgrade/architecture-healthcare-dv-platform-upgrade.md, AD-10
- constraint — /workspaces/GitOps_Iceberg_Data_Platform/_bmad-output/initiative-healthcare-dv-platform-upgrade/architecture-healthcare-dv-platform-upgrade/architecture-healthcare-dv-platform-upgrade.md, AD-14
- constraint — /workspaces/GitOps_Iceberg_Data_Platform/_bmad-output/initiative-healthcare-dv-platform-upgrade/architecture-healthcare-dv-platform-upgrade/architecture-healthcare-dv-platform-upgrade.md, AD-16
- constraint — /workspaces/GitOps_Iceberg_Data_Platform/_bmad-output/initiative-healthcare-dv-platform-upgrade/architecture-healthcare-dv-platform-upgrade/architecture-healthcare-dv-platform-upgrade.md, AD-22
- constraint — /workspaces/GitOps_Iceberg_Data_Platform/_bmad-output/initiative-healthcare-dv-platform-upgrade/architecture-healthcare-dv-platform-upgrade/architecture-healthcare-dv-platform-upgrade.md, AD-24
- input — /workspaces/GitOps_Iceberg_Data_Platform/_bmad-output/initiative-healthcare-dv-platform-upgrade/tickets.toml, [[epic]] id 4 (needs from E1, E3)

## Notes

- Waits on epic-platform-baseline because: it needs the config contract (loader, mapping schema, reason codes), the bytes-cap lint and the D-7 drift key (story-level needs in tickets.toml, not a whole-epic gate).
- Waits on epic-landing-bronze because: it reads reconciled Bronze tables and continues the lifecycle states E3 writes (story-level needs, not a whole-epic gate).
- Decision: 2026-10-07 — user accepted the recommended split; E4 stays one capability epic for CAP-4 with no whole-epic gate (only E3 carries one, on the E1 Bronze smoke).
- Open question: D-7 (data-drift thresholds) is unsettled; E1 ships the key defaulting to "unset, report only", and this epic adopts it.
- Parked: the Gold block on data drift (FR-36 tail, NFR-5), a follow-up story waiting on D-7.
- Parked: deferred PHI hardening under AD-14 (tokenization, restricted dataset, de-identification views, policy tags, audit logs); all data is synthetic.
