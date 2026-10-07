---
type: epic
title: "Single DAG spec, runner and resumability"
parent: initiative-healthcare-dv-platform-upgrade
covers: [CAP-12]
after: []
assignee: ""
risk: medium
---

# Single DAG spec, runner and resumability

## Description

`make e2e-local` runs ingest -> Raw Vault -> MPI -> Business Vault/Gold from one `dag_spec.py`, through a local runner that hardens the E1 run-identity stub: it mints the run ID, holds the per-profile run lock, skips completed stages, loads late files and rebuilds only the affected periods. Workflows and Airflow renderings are generated from the same spec and flagged off. This epic also delivers the FR-40 regression-equality gate that `make upgrade` uses (E1 stays accountable for CAP-16). The intent is CAP-12 in the initiative spec; the requirement lines are FR-27, FR-28, NFR-2, NFR-6, NFR-8 and SM-5 in the requirements catalog.

## Outcome

The platform owner gets one resumable, run-locked pipeline that reruns to identical results and guards every upgrade; a rerun with identical counts, hash-key sets and MPI metrics (NFR-2, SM-5) shows it worked.

## Requirements

Requirements are completed at inception; source is the initiative spec's CAP ids in covers.

## Done when

1. A rerun gives identical row counts, hash-key sets and MPI metrics in vault and Gold, with skipped stages logged (NFR-2, SM-5); a late file loads with its own load date and rebuilds PIT and Gold only for the affected periods.
2. A second concurrent run on the same profile waits or exits, and the runner refuses an 11th Dataproc run.
3. The Workflows and Airflow renderings are generated from `dag_spec.py` and flagged off; the Airflow DAGs import cleanly in the pinned Composer image, with Airflow operators only in the factory.
4. `make upgrade` compares Gold counts, hash-key sets and MPI metrics to the last green run and fails on any difference (FR-40 delivered part).
5. Runs against the demo client project from the CLI (`make e2e-local` with the demo profile), with output in the demo project's GCP datasets, and passes inside `make e2e-chain` at CI volume on the samples with the epics downstream still passing; the CI-volume run finishes in under 45 minutes on a free runner (NFR-8).

## Boundaries

Follows the capability boundary: `pipeline/` (taking over the E1 stub), `dags/`, the writer of `ops.run_events` and `ops.run_lock` (DDL from E1, AD-2), the Dataproc run counter and refusal, and the `vault_loaded` state. Not in scope: the task logic of each layer (E3 to E8), the `ops` DDL (E1), `scheduled-e2e` and all GitHub Actions wiring (E12; E10 provides `make e2e-local`). No logic lives in Actions (NFR-6).

## References

- parent — /workspaces/GitOps_Iceberg_Data_Platform/_bmad-output/initiative-healthcare-dv-platform-upgrade/initiative-healthcare-dv-platform-upgrade.md
- spec — /workspaces/GitOps_Iceberg_Data_Platform/_bmad-output/initiative-healthcare-dv-platform-upgrade/spec-healthcare-dv-platform-upgrade/spec-healthcare-dv-platform-upgrade.md, Capabilities (CAP-12)
- spec — /workspaces/GitOps_Iceberg_Data_Platform/_bmad-output/initiative-healthcare-dv-platform-upgrade/spec-healthcare-dv-platform-upgrade/requirements-catalog.md, CAP-12 (FR-27, FR-28), FR-40, NFR-2, NFR-6, NFR-8, SM-5, SM-6
- constraint — /workspaces/GitOps_Iceberg_Data_Platform/_bmad-output/initiative-healthcare-dv-platform-upgrade/architecture-healthcare-dv-platform-upgrade/architecture-healthcare-dv-platform-upgrade.md, AD-2
- constraint — /workspaces/GitOps_Iceberg_Data_Platform/_bmad-output/initiative-healthcare-dv-platform-upgrade/architecture-healthcare-dv-platform-upgrade/architecture-healthcare-dv-platform-upgrade.md, AD-10
- constraint — /workspaces/GitOps_Iceberg_Data_Platform/_bmad-output/initiative-healthcare-dv-platform-upgrade/architecture-healthcare-dv-platform-upgrade/architecture-healthcare-dv-platform-upgrade.md, AD-16
- constraint — /workspaces/GitOps_Iceberg_Data_Platform/_bmad-output/initiative-healthcare-dv-platform-upgrade/architecture-healthcare-dv-platform-upgrade/architecture-healthcare-dv-platform-upgrade.md, AD-20
- constraint — /workspaces/GitOps_Iceberg_Data_Platform/_bmad-output/initiative-healthcare-dv-platform-upgrade/architecture-healthcare-dv-platform-upgrade/architecture-healthcare-dv-platform-upgrade.md, AD-24
- input — /workspaces/GitOps_Iceberg_Data_Platform/_bmad-output/initiative-healthcare-dv-platform-upgrade/tickets.toml, [[epic]] id 10 (needs from E1, E3, E4, E5, E6, E8)

## Notes

- Waits on epic-platform-baseline because: the runner hardens E1's run-identity stub and writes the `ops.run_events` and `ops.run_lock` tables E1 creates (story-level need, not a whole-epic gate).
- Waits on epic-landing-bronze because: the Bronze landing, WAP and reconcile steps become DAG tasks.
- Waits on epic-silver-normalization because: the Silver normalization and drift steps become DAG tasks.
- Waits on epic-raw-vault because: the Raw Vault build becomes a DAG task and sets `vault_loaded`.
- Waits on epic-mpi because: MPI matching becomes a DAG task and its metrics feed the rerun and upgrade equality checks.
- Waits on epic-business-vault-gold because: the Business Vault, PIT and Gold builds become DAG tasks and late-file rebuild targets.
- Decision: 2026-10-07 — user accepted the recommended split; E10 is not moved earlier: the E1 stub plus `make e2e-chain` gives integration from E3 onward, and the full runner comes once its tasks exist.
- Decision: 2026-10-07 — user accepted the recommended split; CAP-16 stays with E1 as accountable, and E10 delivers the FR-40 regression-equality gate rather than a separate CAP-16 epic.
- Open question: OQ 1 affects only the flagged-off Workflows/Airflow renderer.
