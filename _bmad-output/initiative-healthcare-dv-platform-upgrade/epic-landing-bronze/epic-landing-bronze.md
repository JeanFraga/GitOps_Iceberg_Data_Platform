---
type: epic
title: "Immutable landing, Bronze Iceberg, Spark runtime"
parent: initiative-healthcare-dv-platform-upgrade
covers: [CAP-2, CAP-3, CAP-5]
after: []
assignee: ""
risk: high
---

# Immutable landing, Bronze Iceberg, Spark runtime

## Description

Files land immutably under content-hashed names. Each delivery is written through write-audit-publish (WAP) to one Bronze Iceberg table per (source, feed, era) and passes the reconcile gate before it becomes visible. The same jobs give identical results on local Spark and Dataproc Serverless. This epic is the entry point for every downstream layer (Silver, Raw Vault, MPI, Gold) and the second hop of the tracer path. The intent is CAP-2, CAP-3 and CAP-5 in the initiative spec; the requirement lines are FR-5, FR-6, FR-7 and FR-12 in the requirements catalog.

## Outcome

Pipeline builders get an append-only, reconciled, replayable Bronze replica of every synthetic delivery on either Spark runtime; CAP-2, CAP-3 and CAP-5's acceptance checks (FR-5, FR-6, FR-7, FR-12) are the signal.

## Requirements

Source is the initiative spec's CAP ids in covers (CAP-2: FR-5; CAP-3: FR-6, FR-7; CAP-5: FR-12) plus NFR-4 (loader refuses unmarked files) and FR-35 (scan over this epic's logs and summaries). Entries and their covers are in tickets.toml beside this file.

## Done when

1. Landing is immutable: an overwrite is rejected and logged, a duplicate hash becomes `rejected_duplicate`, Coldline (7 days) and Archive (60 days) transitions are logged, and an unmarked file is refused by the loader and logged (NFR-4).
2. Bronze is append-only and gated: a reload appends 0 rows, each delivery is one snapshot tagged with run ID and file hash, an unknown fingerprint goes to `unmapped_<fp8>`, and a reconcile failure quarantines the file with `RECONCILE_FAIL`.
3. EDI pre-parse output is byte-identical on regeneration, checked in CI on the samples.
4. Local Spark and Dataproc outputs on the same input are identical; the runner refuses an over-cap Dataproc run, the TTL guard tears down after each run, and the opt-in full-size datagen run on Dataproc writes to landing within its cost ceiling.
5. The FR-35 scan over this epic's logs and summaries is clean, with a canary seeded in the input.
6. Runs against the demo client project from the CLI (`make <target>` with the demo profile), with output in the demo project's GCP datasets, and passes inside `make e2e-chain` at CI volume on the samples with the epics downstream still passing.

## Boundaries

Follows the capability boundary: landing, `edi/` pre-parse, the WAP writer, reconcile, the storage-class reconciler, the runtime switch, Dataproc caps and batch TTL, the Dataproc SA and its Terraform (on E1's module pattern), and `ops.file_lifecycle` writes up to `reconciled`. Not in scope: the `ops.*` DDL, `fingerprint.py`, `lifecycle.yaml`, the marker rule and the FR-35 scanner (E1); emitting the marker (E2); `silver_loaded`, quarantine replay, and Silver-side drift reports (cast failures, data drift) (E4); `ops.run_lock` and the hardened runner (E10). Per AD-2 and AD-5 the loader writes `ops.drift_report` rows for unmapped and additive eras, and the Dataproc run counter is appended to `ops.run_events` through the existing pipeline/runner.py. PHI hardening is out of scope (see the spec's Non-goals).

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

- Waits on epic-platform-baseline because: it needs `fingerprint.py`, `lifecycle.yaml`, buckets, catalog, the run-identity stub and the marker rule.
- Waits on epic-synthetic-data because: it needs the committed samples (story-level need in tickets.toml, not a whole-epic gate).
- Decision: 2026-10-07 — user accepted the recommended split; this epic stays whole for CAP-2, CAP-3 and CAP-5 and carries the only whole-epic gate, on the E1 Bronze smoke.
- Parked: deferred PHI hardening under AD-14 (tokenization, restricted dataset, de-identification views, policy tags, audit logs, delete locks); all data is synthetic.
- Decision: the whole-epic gate on E1 was removed since the Bronze smoke was dropped; entries pin 1.4, 1.6, 1.7 and 1.10 instead. OQ 2, 3 and 5 risk lands on the first Bronze story (2026-10-07).
- Tracer bullet: entry 1 lands one committed sample CSV, loads it with local Spark into a Bronze Iceberg table in the BigLake REST catalog, reads it from BigQuery and writes `ops.file_lifecycle`; it carries the OQ 2/3/5 risk (BigLake REST on runtime 3.0 with Iceberg 1.12.0) and has a plan checkpoint. Entry 2 (WAP and the reconcile gate) is next as the least certain piece. Entries 1-5 are one loader lane in order; entry 6 (EDI pre-parse) runs beside it once entry 1 has created the `ingestion/` package; entry 7 follows entry 4; entries 8-10 are the Dataproc lane after entry 5; entry 11 closes the chain; entry 12 is the Refactor sweep. No closing end-to-end suite: `make e2e-chain` (entry 11) is the epic's end-to-end check.
- Decision: 2026-10-08 — the opt-in Dataproc full-size datagen run (FR-1), parked by epic-synthetic-data, is entry 10 of this epic, since it needs this epic's Dataproc submit path and Done when 4 names it. Assumption (autonomous inception).
- Decision: 2026-10-08 — generated CSVs start with a `# SYNTHETIC-DATA-NO-REAL-PHI` marker line; the loader checks the marker and drops that line before calling config/fingerprint.py, which would otherwise read it as the header. Assumption (autonomous inception).
- Decision: 2026-10-08 — `_line_ordinal` is the 1-based physical line number in the landed file for CSV and NDJSON (marker and header lines counted), matching the datagen manifest's first-affected-record numbering; for X12 it is the 1-based segment ordinal (split on ISA16), since X12 files need not be line-broken. Assumption (autonomous inception).
- Decision: 2026-10-08 — the era registry lives in `config/eras/<source>.yaml` (feed, era, fingerprint, columns); E4's `config/mappings/<source>/<feed>_<era>.yaml` keys off the same era names. Assumption (autonomous inception).
- Decision: 2026-10-08 — an overwrite rejection and an unmarked-file refusal are logged as structured JSON log lines (no row values); no lifecycle state is added, since `lifecycle.yaml` is closed and E1-owned. Assumption (autonomous inception).
- Decision: 2026-10-08 — the Dataproc run counter is appended to `ops.run_events` through the existing pipeline/runner.py (the AD-2 writer of run_events); E10 hardens the runner. Assumption (autonomous inception).
- Decision: 2026-10-08 — the EDI pre-parse derivative is written to the warehouse bucket under `edi_preparse/` and checked byte-identical in CI against committed goldens from the samples; whether Silver reads it from there or from a Bronze table is E4's choice. Assumption (autonomous inception).
- Decision: 2026-10-08 — `make e2e-chain` is created by entry 11 as the chain later epics append to (E10's Decision expects integration from E3 onward). Assumption (autonomous inception).
- Decision: 2026-10-08 — the devcontainer ships Java 17 today; entry 1 moves it to Java 21 to match Dataproc runtime 3.0 (AD-17). Assumption (autonomous inception).
- Open: the full-size run of 2026-10-08 (~182 MB under ingest_date=2026-10-08 in gs://gitops-iceberg-data-platform-landing) is not loaded to Bronze by any entry; the CI-volume chain loads the samples only. Loading it is a single `make bronze PROFILE=demo` once entry 5 is done, if the owner wants it within NFR-1.
- Decision: 2026-10-08 — Boundaries amended to match AD-2/AD-5 (loader writes era drift_report rows) and AD-16 (Dataproc counter through pipeline/runner.py); the stale smoke-gate wording was dropped. Assumption (autonomous inception).
- Decision: 2026-10-08 — entry 10 covers CAP-5 only (the FR-12 runtime part of the parked FR-1 Dataproc path); CAP-1 stays with epic-synthetic-data and is not added to this epic's covers. Assumption (autonomous inception).
