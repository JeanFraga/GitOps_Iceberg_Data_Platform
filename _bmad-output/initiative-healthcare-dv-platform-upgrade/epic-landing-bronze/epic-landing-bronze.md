---
type: epic
title: "Immutable landing, Bronze Iceberg, Spark runtime"
parent: initiative-healthcare-dv-platform-upgrade
covers: [CAP-2, CAP-3, CAP-5]
after: [epic-platform-baseline]
assignee: ""
risk: high
---

# Immutable landing, Bronze Iceberg, Spark runtime

## Description

Files land immutably under content-hashed names. Each delivery is written through write-audit-publish (WAP) to one Bronze Iceberg table per (source, feed, era) and passes the reconcile gate before it becomes visible. The same jobs give identical results on local Spark and Dataproc Serverless. This epic is the entry point for every downstream layer (Silver, Raw Vault, MPI, Gold) and the second hop of the tracer path. The intent is CAP-2, CAP-3 and CAP-5 in the initiative spec; the requirement lines are FR-5, FR-6, FR-7 and FR-12 in the requirements catalog.

## Outcome

Pipeline builders get an append-only, reconciled, replayable Bronze replica of every synthetic delivery on either Spark runtime; CAP-2, CAP-3 and CAP-5's acceptance checks (FR-5, FR-6, FR-7, FR-12) are the signal.

## Requirements

Requirements are completed at inception; source is the initiative spec's CAP ids in covers.

## Done when

1. Landing is immutable: an overwrite is rejected and logged, a duplicate hash becomes `rejected_duplicate`, Coldline (7 days) and Archive (60 days) transitions are logged, and an unmarked file is refused by the loader and logged (NFR-4).
2. Bronze is append-only and gated: a reload appends 0 rows, each delivery is one snapshot tagged with run ID and file hash, an unknown fingerprint goes to `unmapped_<fp8>`, and a reconcile failure quarantines the file with `RECONCILE_FAIL`.
3. EDI pre-parse output is byte-identical on regeneration, checked in CI on the samples.
4. Local Spark and Dataproc outputs on the same input are identical; the runner refuses an over-cap Dataproc run, the TTL guard tears down after each run, and the opt-in full-size datagen run on Dataproc writes to landing within its cost ceiling.
5. The FR-35 scan over this epic's logs and summaries is clean, with a canary seeded in the input.
6. Runs against the demo client project from the CLI (`make <target>` with the demo profile), with output in the demo project's GCP datasets, and passes inside `make e2e-chain` at CI volume on the samples with the epics downstream still passing.

## Boundaries

Follows the capability boundary: landing, `edi/` pre-parse, the WAP writer, reconcile, the storage-class reconciler, the runtime switch, Dataproc caps and batch TTL, the Dataproc SA and its Terraform (on E1's module pattern), and `ops.file_lifecycle` writes up to `reconciled`. Not in scope: the `ops.*` DDL, `fingerprint.py`, `lifecycle.yaml`, the marker rule and the FR-35 scanner (E1); emitting the marker (E2); `silver_loaded`, quarantine replay and drift reports (E4); `ops.run_events` and `ops.run_lock` writes and the hardened runner (E10). PHI hardening is out of scope (see the spec's Non-goals).

## References

- parent — /workspaces/GitOps_Iceberg_Data_Platform/_bmad-output/initiative-healthcare-dv-platform-upgrade/initiative-healthcare-dv-platform-upgrade.md
- spec — /workspaces/GitOps_Iceberg_Data_Platform/_bmad-output/initiative-healthcare-dv-platform-upgrade/spec-healthcare-dv-platform-upgrade/spec-healthcare-dv-platform-upgrade.md, Capabilities (CAP-2, CAP-3, CAP-5)
- spec — /workspaces/GitOps_Iceberg_Data_Platform/_bmad-output/initiative-healthcare-dv-platform-upgrade/spec-healthcare-dv-platform-upgrade/requirements-catalog.md, CAP-2 (FR-5), CAP-3 (FR-6, FR-7), CAP-5 (FR-12), NFR-4, FR-35
- constraint — /workspaces/GitOps_Iceberg_Data_Platform/_bmad-output/initiative-healthcare-dv-platform-upgrade/architecture-healthcare-dv-platform-upgrade/architecture-healthcare-dv-platform-upgrade.md, AD-1
- constraint — /workspaces/GitOps_Iceberg_Data_Platform/_bmad-output/initiative-healthcare-dv-platform-upgrade/architecture-healthcare-dv-platform-upgrade/architecture-healthcare-dv-platform-upgrade.md, AD-2
- constraint — /workspaces/GitOps_Iceberg_Data_Platform/_bmad-output/initiative-healthcare-dv-platform-upgrade/architecture-healthcare-dv-platform-upgrade/architecture-healthcare-dv-platform-upgrade.md, AD-3
- constraint — /workspaces/GitOps_Iceberg_Data_Platform/_bmad-output/initiative-healthcare-dv-platform-upgrade/architecture-healthcare-dv-platform-upgrade/architecture-healthcare-dv-platform-upgrade.md, AD-5
- constraint — /workspaces/GitOps_Iceberg_Data_Platform/_bmad-output/initiative-healthcare-dv-platform-upgrade/architecture-healthcare-dv-platform-upgrade/architecture-healthcare-dv-platform-upgrade.md, AD-6
- constraint — /workspaces/GitOps_Iceberg_Data_Platform/_bmad-output/initiative-healthcare-dv-platform-upgrade/architecture-healthcare-dv-platform-upgrade/architecture-healthcare-dv-platform-upgrade.md, AD-7
- constraint — /workspaces/GitOps_Iceberg_Data_Platform/_bmad-output/initiative-healthcare-dv-platform-upgrade/architecture-healthcare-dv-platform-upgrade/architecture-healthcare-dv-platform-upgrade.md, AD-9
- constraint — /workspaces/GitOps_Iceberg_Data_Platform/_bmad-output/initiative-healthcare-dv-platform-upgrade/architecture-healthcare-dv-platform-upgrade/architecture-healthcare-dv-platform-upgrade.md, AD-10
- constraint — /workspaces/GitOps_Iceberg_Data_Platform/_bmad-output/initiative-healthcare-dv-platform-upgrade/architecture-healthcare-dv-platform-upgrade/architecture-healthcare-dv-platform-upgrade.md, AD-14
- constraint — /workspaces/GitOps_Iceberg_Data_Platform/_bmad-output/initiative-healthcare-dv-platform-upgrade/architecture-healthcare-dv-platform-upgrade/architecture-healthcare-dv-platform-upgrade.md, AD-16
- constraint — /workspaces/GitOps_Iceberg_Data_Platform/_bmad-output/initiative-healthcare-dv-platform-upgrade/architecture-healthcare-dv-platform-upgrade/architecture-healthcare-dv-platform-upgrade.md, AD-22
- constraint — /workspaces/GitOps_Iceberg_Data_Platform/_bmad-output/initiative-healthcare-dv-platform-upgrade/architecture-healthcare-dv-platform-upgrade/architecture-healthcare-dv-platform-upgrade.md, AD-24
- input — /workspaces/GitOps_Iceberg_Data_Platform/_bmad-output/initiative-healthcare-dv-platform-upgrade/tickets.toml, [[epic]] id 3 (needs from E1 and E2)

## Notes

- Waits on epic-platform-baseline because: the Bronze smoke gate (runtime 3.0, Iceberg 1.12.0: create, append, BigQuery read) must pass with owner review before any E3 work starts, since an OQ 2/3 failure reshapes this epic; it also needs `fingerprint.py`, `lifecycle.yaml`, buckets, catalog, the run-identity stub and the marker rule.
- Waits on epic-synthetic-data because: it needs the committed samples (story-level need in tickets.toml, not a whole-epic gate).
- Decision: 2026-10-07 — user accepted the recommended split; this epic stays whole for CAP-2, CAP-3 and CAP-5 and carries the only whole-epic gate, on the E1 Bronze smoke.
- Unknown: OQ 2 and OQ 3 are resolved as E1 smoke-gate outcomes; their results set this epic's high risk and may reshape it.
- Parked: deferred PHI hardening under AD-14 (tokenization, restricted dataset, de-identification views, policy tags, audit logs, delete locks); all data is synthetic.
