---
type: epic
title: "Synthetic healthcare data generator"
parent: initiative-healthcare-dv-platform-upgrade
covers: [CAP-1]
after: []
assignee: ""
risk: medium
---

# Synthetic healthcare data generator

## Description

`make generate` deterministically produces every feed, era, schema-drift scenario, data-drift sample and identity-noise case, plus the manifest and `mpi_eval.ground_truth`, at CI size and at full size locally. The 1,000-record samples and the generator README are committed. Every downstream epic (landing, Silver, Raw Vault, MPI) builds and tests against this output, so it is the data source for the whole tracer path. The intent is CAP-1 in the initiative spec; the requirement lines are FR-1 to FR-4, FR-36 and FR-37 in the requirements catalog.

## Outcome

Pipeline builders and the MPI evaluation get reproducible, source-shaped synthetic data with known drift and known truth; CAP-1's signals (SM-4, SM-9, SM-C3, mapping to be confirmed) show it worked.

## Requirements

Requirements are completed at inception; source is the initiative spec's CAP ids in covers.

## Done when

1. The same seed and parameters give the same SHA-256 across two runs, and every generated file carries the synthetic marker.
2. The manifest lists all 5 schema-drift scenarios and the data-drift samples with scenario, source, file and first affected record; the edge-case rate is 2% ± 0.5 pp, and the evaluation seed has at least one noise scenario the training seed lacks.
3. NPIs pass Luhn, all 3 NDC forms (4-4-2, 5-3-2, 5-4-1) are present, and claim versions 1, 7 and 8 are present.
4. There is exactly one 1,000-record sample per feed, and CI fails on an oversized committed data file.
5. Runs against the demo client project from the CLI (`make generate` with the demo profile), with output in the demo project's GCP datasets, and passes inside `make e2e-chain` at CI volume on the samples with the epics downstream still passing.

## Boundaries

Follows the capability boundary: `datagen/` and the committed samples. It writes only to the landing zone and `mpi_eval.ground_truth`. FR-36 is split: this epic delivers the data-drift samples and manifest entries; per-file profiles and flagging belong to `epic-silver-normalization` (E4), and the Gold drift block is parked. The synthetic-marker rule and its CI check are E1's; this epic only emits the marker, and E3's loader refuses unmarked files. Not in scope: PHI hardening (see the spec's Non-goals).

## References

- parent — /workspaces/GitOps_Iceberg_Data_Platform/_bmad-output/initiative-healthcare-dv-platform-upgrade/initiative-healthcare-dv-platform-upgrade.md
- spec — /workspaces/GitOps_Iceberg_Data_Platform/_bmad-output/initiative-healthcare-dv-platform-upgrade/spec-healthcare-dv-platform-upgrade/spec-healthcare-dv-platform-upgrade.md, Capabilities (CAP-1)
- spec — /workspaces/GitOps_Iceberg_Data_Platform/_bmad-output/initiative-healthcare-dv-platform-upgrade/spec-healthcare-dv-platform-upgrade/requirements-catalog.md, CAP-1 (FR-1..FR-4, FR-36, FR-37), NFR-4, SM-4, SM-9, SM-C3
- constraint — /workspaces/GitOps_Iceberg_Data_Platform/_bmad-output/initiative-healthcare-dv-platform-upgrade/architecture-healthcare-dv-platform-upgrade/architecture-healthcare-dv-platform-upgrade.md, AD-14
- constraint — /workspaces/GitOps_Iceberg_Data_Platform/_bmad-output/initiative-healthcare-dv-platform-upgrade/architecture-healthcare-dv-platform-upgrade/architecture-healthcare-dv-platform-upgrade.md, AD-1
- constraint — /workspaces/GitOps_Iceberg_Data_Platform/_bmad-output/initiative-healthcare-dv-platform-upgrade/architecture-healthcare-dv-platform-upgrade/architecture-healthcare-dv-platform-upgrade.md, AD-3
- constraint — /workspaces/GitOps_Iceberg_Data_Platform/_bmad-output/initiative-healthcare-dv-platform-upgrade/architecture-healthcare-dv-platform-upgrade/architecture-healthcare-dv-platform-upgrade.md, AD-5
- constraint — /workspaces/GitOps_Iceberg_Data_Platform/_bmad-output/initiative-healthcare-dv-platform-upgrade/architecture-healthcare-dv-platform-upgrade/architecture-healthcare-dv-platform-upgrade.md, AD-16
- input — /workspaces/GitOps_Iceberg_Data_Platform/_bmad-output/initiative-healthcare-dv-platform-upgrade/tickets.toml, [[epic]] id 2 (needs from E1)

## Notes

- Waits on epic-platform-baseline because: it needs the config loader, region, landing bucket, synthetic-marker rule, `mpi_eval` DDL and bytes caps (story-level needs in tickets.toml, not a whole-epic gate).
- Decision: 2026-10-07 — user accepted the recommended split; this epic stays one capability epic for CAP-1, and only E3 carries a whole-epic gate (on the E1 Bronze smoke).
- Source conflict: CAP-1 metrics line in the spec reads "SM-3? No: SM-4, SM-9, SM-C3", which looks garbled; confirm the mapping before Done when is finalized at inception.
- Parked: the Gold block on data drift (FR-36 tail), a follow-up story waiting on D-7.
- Parked: deferred PHI hardening under AD-14 (tokenization, restricted dataset, de-identification views, policy tags, audit logs); all data is synthetic.
- Unknown: X12 shapes (837P/I/D, 834, 835 per FR-2) carry most of the effort and set the risk at medium.
