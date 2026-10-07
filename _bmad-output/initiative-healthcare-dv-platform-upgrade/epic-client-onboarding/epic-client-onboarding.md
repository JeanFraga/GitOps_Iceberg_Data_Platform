---
type: epic
title: "Client profile proof (Payer C)"
parent: initiative-healthcare-dv-platform-upgrade
covers: [CAP-13]
after: []
assignee: ""
risk: medium
---

# Client profile proof (Payer C)

## Description

A new client source (Payer C) is onboarded purely through configuration: a Payer C profile and mappings under `config/clients/`, bound through the onboarding CLI around `fingerprint.py`, run the full pipeline at CI volume with zero diff outside `config/`. This proves the single YAML contract and the one-project-per-client model hold, and surfaces any hidden per-source logic left in earlier epics. The intent is CAP-13 in the initiative spec; the requirement line is FR-29 (with UJ-1, SM-2, SM-C4) in the requirements catalog.

## Outcome

Platform owners can onboard a new payer by editing `config/` only; the Payer C CI job passing with zero diff outside `config/` (SM-2) is the signal.

## Requirements

Requirements are completed at inception; source is the initiative spec's CAP ids in covers.

## Done when

1. The Payer C CI job passes the full pipeline at CI volume with zero diff outside `config/` (SM-2), and both the demo and template profiles are validated in CI (FR-29).
2. A scan finds 0 per-source code branches (SM-C4).
3. The UJ-1 additive-column case (maps to the existing era with padding and a drift_report row) and the unmapped-era replay case (bind the fingerprint in config, Silver reads `unmapped_<fp8>` under the bound era) both pass.
4. Runs against the demo client project from the CLI (`make <target>` with the demo profile), with output in the demo project's GCP datasets, and passes inside `make e2e-chain` at CI volume on the samples with the epics downstream still passing.

## Boundaries

Follows the capability boundary for client onboarding: `config/clients/`, the Payer C mappings, the onboarding CLI around `fingerprint.py`, and the Payer C CI job. Not in scope: the `config/` loader and the FR-29 contract itself (E1), the fingerprint algorithm and Bronze era authority (E3), Silver mapping logic (E4), the runner and `make e2e-local` (E10), the GitHub Actions workflows (E12). A second client in its own GCP project and the onboarding guide (FR-30) are Phase 2.

## References

- parent — /workspaces/GitOps_Iceberg_Data_Platform/_bmad-output/initiative-healthcare-dv-platform-upgrade/initiative-healthcare-dv-platform-upgrade.md
- spec — /workspaces/GitOps_Iceberg_Data_Platform/_bmad-output/initiative-healthcare-dv-platform-upgrade/spec-healthcare-dv-platform-upgrade/spec-healthcare-dv-platform-upgrade.md, Capabilities (CAP-13)
- spec — /workspaces/GitOps_Iceberg_Data_Platform/_bmad-output/initiative-healthcare-dv-platform-upgrade/spec-healthcare-dv-platform-upgrade/requirements-catalog.md, CAP-13 (FR-29), SM-2, SM-C4, UJ-1
- constraint — /workspaces/GitOps_Iceberg_Data_Platform/_bmad-output/initiative-healthcare-dv-platform-upgrade/architecture-healthcare-dv-platform-upgrade/architecture-healthcare-dv-platform-upgrade.md, AD-1
- constraint — /workspaces/GitOps_Iceberg_Data_Platform/_bmad-output/initiative-healthcare-dv-platform-upgrade/architecture-healthcare-dv-platform-upgrade/architecture-healthcare-dv-platform-upgrade.md, AD-5
- constraint — /workspaces/GitOps_Iceberg_Data_Platform/_bmad-output/initiative-healthcare-dv-platform-upgrade/architecture-healthcare-dv-platform-upgrade/architecture-healthcare-dv-platform-upgrade.md, AD-19
- constraint — /workspaces/GitOps_Iceberg_Data_Platform/_bmad-output/initiative-healthcare-dv-platform-upgrade/architecture-healthcare-dv-platform-upgrade/architecture-healthcare-dv-platform-upgrade.md, AD-22
- input — /workspaces/GitOps_Iceberg_Data_Platform/_bmad-output/initiative-healthcare-dv-platform-upgrade/tickets.toml, [[epic]] id 11 (needs from E1, E10)

## Notes

- Waits on epic-platform-baseline because: it needs the profile template and the FR-29 config contract (story-level need in tickets.toml, not a whole-epic gate).
- Waits on epic-orchestration because: the Payer C job runs through the runner and `make e2e-local` (story-level need, not a whole-epic gate).
- Decision: 2026-10-07 — user accepted the recommended split; E1 stays whole (it owns the FR-29 contract this epic proves), and only E3 carries a whole-epic gate (on the E1 Bronze smoke), so this epic has `after: []`.
- Parked: FR-30 (onboarding guide, Phase 2), deferred inside CAP-13; its steps must later match the Payer C job.
- Parked: deferred PHI hardening under AD-14; all data is synthetic.
- Risk: medium — the zero-diff proof surfaces any hidden per-source logic in earlier epics, which may push fixes back into E3, E4 or E5.
