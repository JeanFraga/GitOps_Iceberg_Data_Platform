---
type: epic
title: "MPI, evaluation harness and retrain gate"
parent: initiative-healthcare-dv-platform-upgrade
covers: [CAP-8]
after: []
assignee: ""
risk: high
---

# MPI, evaluation harness and retrain gate

## Description

Every member and patient record resolves to exactly one `HUB_PERSON` golden key, scored by Splink with an XGBoost fallback for edge pairs, closed transitively under must-not-link, and recorded insert-only with merges and splits as effectivity rows. An evaluation harness measures quality on the held-out evaluation seed, and models are promoted only through a retrain gate that also consumes steward decisions from E7. Business Vault and Gold key on this golden key. The intent is CAP-8 in the initiative spec; the requirement lines are FR-16 to FR-19 in the requirements catalog.

## Outcome

Downstream Gold consumers get one stable person per real individual across payer and EMR feeds; CAP-8's signals SM-1, SM-C1 and SM-7 on the evaluation seed show it worked.

## Requirements

Requirements are completed at inception; source is the initiative spec's CAP ids in covers.

## Done when

1. On the evaluation seed, pairwise F1 is at least 0.97 overall and at least 0.90 on edge cases (SM-1), false merges after closure are at most 0.5% (SM-C1) and the queue holds at most 3% of true-match pairs (SM-7); pairwise and B-cubed metrics are written to `mpi_eval.metrics` and the CI summary.
2. The train/test split is at person level, ground truth is never readable as a feature, and every score row carries `model_version` and `threshold_set_version`; with the fallback off every edge pair is queued, a previous model can be restored, and the model bucket is runtime-SA only.
3. Must-not-link holds after closure, an oversized cluster is queued, and `HUB_PERSON` covers members and patients (EMR plus payer gives one person); an identical rerun inserts nothing, merges and un-merges are recorded in the `LINK_PERSON_SAME_AS` effectivity satellite, and a steward decision applied twice by `decision_id` changes nothing.
4. The retrain gate promotes only when the new model beats the current one on the evaluation seed, false merges stay within SM-C1 and F1 does not drop; evaluation-seed decisions are excluded from training.
5. The FR-35 scan is clean over MPI CI summaries and `mpi_eval`, with a canary seeded in the input.
6. Runs against the demo client project from the CLI (`make <target>` with the demo profile), with output in the demo project's GCP datasets, and passes inside `make e2e-chain` at CI volume on the samples with the epics downstream still passing.

## Boundaries

Follows the capability boundary: `mpi/` (scoring, fallback, golden key writer, eval harness, retrain gate, applying steward decisions), the MPI tables including `HUB_PERSON` (MPI-owned under AD-13), `steward.review_queue`, the `mpi_complete` event, and the model bucket resource built on E1's module pattern. It sets its own bytes cap under E1's lint. Not in scope: the steward UI and `steward.decision` (E7); `ops.*`, `steward` and `mpi_eval` DDL (E1); ground truth and seeds (E2); member and patient hubs and satellites (E5); Business Vault and Gold (E8). PHI hardening is out of scope (see the spec's Non-goals).

## References

- parent — /workspaces/GitOps_Iceberg_Data_Platform/_bmad-output/initiative-healthcare-dv-platform-upgrade/initiative-healthcare-dv-platform-upgrade.md
- spec — /workspaces/GitOps_Iceberg_Data_Platform/_bmad-output/initiative-healthcare-dv-platform-upgrade/spec-healthcare-dv-platform-upgrade/spec-healthcare-dv-platform-upgrade.md, Capabilities (CAP-8)
- spec — /workspaces/GitOps_Iceberg_Data_Platform/_bmad-output/initiative-healthcare-dv-platform-upgrade/spec-healthcare-dv-platform-upgrade/requirements-catalog.md, CAP-8 (FR-16..FR-19), FR-35, SM-1, SM-5, SM-7, SM-C1, D-1
- constraint — /workspaces/GitOps_Iceberg_Data_Platform/_bmad-output/initiative-healthcare-dv-platform-upgrade/architecture-healthcare-dv-platform-upgrade/architecture-healthcare-dv-platform-upgrade.md, AD-1
- constraint — /workspaces/GitOps_Iceberg_Data_Platform/_bmad-output/initiative-healthcare-dv-platform-upgrade/architecture-healthcare-dv-platform-upgrade/architecture-healthcare-dv-platform-upgrade.md, AD-2
- constraint — /workspaces/GitOps_Iceberg_Data_Platform/_bmad-output/initiative-healthcare-dv-platform-upgrade/architecture-healthcare-dv-platform-upgrade/architecture-healthcare-dv-platform-upgrade.md, AD-6
- constraint — /workspaces/GitOps_Iceberg_Data_Platform/_bmad-output/initiative-healthcare-dv-platform-upgrade/architecture-healthcare-dv-platform-upgrade/architecture-healthcare-dv-platform-upgrade.md, AD-7
- constraint — /workspaces/GitOps_Iceberg_Data_Platform/_bmad-output/initiative-healthcare-dv-platform-upgrade/architecture-healthcare-dv-platform-upgrade/architecture-healthcare-dv-platform-upgrade.md, AD-13
- constraint — /workspaces/GitOps_Iceberg_Data_Platform/_bmad-output/initiative-healthcare-dv-platform-upgrade/architecture-healthcare-dv-platform-upgrade/architecture-healthcare-dv-platform-upgrade.md, AD-16
- constraint — /workspaces/GitOps_Iceberg_Data_Platform/_bmad-output/initiative-healthcare-dv-platform-upgrade/architecture-healthcare-dv-platform-upgrade/architecture-healthcare-dv-platform-upgrade.md, AD-23
- constraint — /workspaces/GitOps_Iceberg_Data_Platform/_bmad-output/initiative-healthcare-dv-platform-upgrade/architecture-healthcare-dv-platform-upgrade/architecture-healthcare-dv-platform-upgrade.md, AD-25
- input — /workspaces/GitOps_Iceberg_Data_Platform/_bmad-output/initiative-healthcare-dv-platform-upgrade/tickets.toml, [[epic]] id 6 (needs from E1, E2, E5)

## Notes

- Waits on epic-platform-baseline because: it needs the `mpi_eval` and `steward` DDL, the model bucket module pattern, `ml_fallback_enabled` and the bytes-cap lint (story-level needs in tickets.toml, not a whole-epic gate).
- Waits on epic-synthetic-data because: the eval harness and training need ground truth and both seeds (story-level needs, not a whole-epic gate).
- Waits on epic-raw-vault because: scoring reads the member and patient hubs and satellites (story-level needs, not a whole-epic gate).
- Decision: 2026-10-07 — user accepted the recommended split; E6 and E7 stay separate, with the retrain gate in E6 consuming E7's `steward.decision` rows (only the gate stories wait on E7). Merge only if one person builds both.
- Open question: D-1 (Splink backend, default DuckDB extract and load-back) is decided here; revisit if the default-volume MPI run exceeds free-runner memory or the Splink 5 API check fails.
- Unknown: Splink 5.0.0 API changes from v4 (unverified); the scoring stories wait on it.
- Source conflict: CAP-6 hub list omits `HUB_PERSON`, which is MPI-owned under AD-13 and built here; fix the catalog text.
- Source conflict: `ml_fallback_enabled` is grouped with the cost flags but defaults on; consistent with AD-1, noted only.
- Parked: deferred PHI hardening under AD-14 (tokenization, restricted dataset, de-identification views, policy tags, audit logs); all data is synthetic.
