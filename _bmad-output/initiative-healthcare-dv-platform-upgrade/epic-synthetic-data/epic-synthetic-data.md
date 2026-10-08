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

Pipeline builders and the MPI evaluation get reproducible, source-shaped synthetic data with known drift and known truth; CAP-1's signals (SM-4, SM-9, SM-C3) show it worked.

## Requirements

Source: CAP-1 in the requirements catalog; every entry covers CAP-1, broken down by line:

- FR-1 deterministic population, pluggable feeds, volume_profile, marker: entries 1, 9
- FR-2 source shapes per era: entries 2 (837P/I/D, versions, Luhn NPIs), 3 (834, 835), 4 (NCPDP CSV, NDC forms, providers), 5 (FHIR NDJSON); flat payer CSV in 1
- FR-3 schema drift injection: entry 7
- FR-4 identity noise and ground truth: entries 1 (ground truth path), 6 (noise, edge-case rate, held-out eval seed)
- FR-36 data drift samples (generator half only): entry 8
- FR-37 samples, README, repo-weight guard: entry 10
- NFR-4 marker emitted on every file: every entry; SM-4, SM-9, SM-C3 are the signals

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
- constraint — /workspaces/GitOps_Iceberg_Data_Platform/_bmad-output/initiative-healthcare-dv-platform-upgrade/architecture-healthcare-dv-platform-upgrade/architecture-healthcare-dv-platform-upgrade.md, AD-25
- input — /workspaces/GitOps_Iceberg_Data_Platform/_bmad-output/initiative-healthcare-dv-platform-upgrade/tickets.toml, [[epic]] id 2 (needs from E1)

## Notes

- Waits on epic-platform-baseline because: it needs the config loader, region, landing bucket, synthetic-marker rule, `mpi_eval` DDL and bytes caps (story-level needs in tickets.toml, not a whole-epic gate).
- Decision: 2026-10-07 — user accepted the recommended split; this epic stays one capability epic for CAP-1, and only E3 carries a whole-epic gate (on the E1 Bronze smoke).
- Resolved 2026-10-08: the requirements catalog tags SM-4, SM-9 and SM-C3 with CAP-1, settling the garbled metrics line in the spec.
- Parked: the Gold block on data drift (FR-36 tail), a follow-up story waiting on D-7.
- Parked: deferred PHI hardening under AD-14 (tokenization, restricted dataset, de-identification views, policy tags, audit logs); all data is synthetic.
- Unknown: X12 shapes (837P/I/D, 834, 835 per FR-2) carry most of the effort and set the risk at medium.
- Decision: 2026-10-08 — incepted into 11 entries, tracer bullet first (Payer B member CSV end to end to landing and `mpi_eval.ground_truth`), X12 claims next as the least certain work, closing Refactor sweep; no closing end-to-end suite (no test plan in the source). Assumption (autonomous inception).
- Decision: 2026-10-08 — the Dataproc opt-in path for full-size runs (FR-1) is parked as a follow-up story that waits on epic-landing-bronze's Spark runtime; this epic's full-size run is local from the devcontainer and streams to landing. Assumption (autonomous inception).
- Decision: 2026-10-08 — config keys are `datagen.seed`, `datagen.eval_seed`, `datagen.volume_profile` (`ci`, `full`), `datagen.edge_case_rate`, `datagen.eval_only_scenarios`; local output in gitignored `datagen/out/`, upload by `make generate-upload`; 834/837/835 belong to Payer A, flat CSV to Payer B. Assumption (autonomous inception).
- Decision: 2026-10-08 — Done when 5's `make e2e-chain` does not exist yet and is owned by a later epic; this epic is checked by `make generate` and `make samples` on the demo profile, and joins `make e2e-chain` when that target lands. Assumption (autonomous inception).
- Decision: 2026-10-08 — plan_checkpoint and done_checkpoint left unset (false) on every entry; entry 2 (X12 837) is high risk but self-checking through round-trip parse tests. Assumption (autonomous inception).
- Unknown: the repo-weight size limit (bytes) for FR-37 is not set in the source; entry 10 picks a limit in config/standards/guardrails.yaml and records it.
- Parked: the opt-in Dataproc path for full-size runs (FR-1) and its README section (FR-37), a follow-up story waiting on epic-landing-bronze's Spark runtime; entries 9 and 10 cover local full-size runs only.
- Decision: 2026-10-08 — entries 6, 7 and 8 (noise, schema drift, data drift) each wait on every feed (3, 4, 5) because they act on all feeds, and run in parallel through the plugin registry and manifest/ground-truth contract fixed in entry 1; entry 9 waits on all three. Assumption (autonomous inception).
- Decision: 2026-10-08 — the Gold drift block (FR-36 tail, D-7) stays parked outside CAP-1 closure for this epic. Assumption (autonomous inception).
