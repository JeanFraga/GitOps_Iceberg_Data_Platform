---
tracker_id: ""
key: ""
type: epic
title: "Platform baseline, migration, config contract and guardrails"
parent: initiative-healthcare-dv-platform-upgrade
covers: [CAP-14, CAP-16]
after: []
assignee: ""
risk: high
---

# Platform baseline, migration, config contract and guardrails

## Description

The taxi platform is preserved on `v1` and removed from main and GCP, and the demo project is rebuilt from the CLI on Terraform 1.16.5 with Google providers 8.6.0. The config contract (FR-29) and its golden vectors exist, the cost and PHI guardrails are enforced before the first BigQuery spend, the Fusion and Bronze smoke gates have passed with owner review, a run-identity stub mints `run_id` and takes the run lock, and `make upgrade` is the only upgrade path. Every later epic builds on this baseline. See the initiative spec, CAP-14 and CAP-16, plus FR-29, FR-35, FR-40, NFR-9 and SM-3 in the requirements catalog.

## Outcome

The platform owner can apply, guard and upgrade the demo project from the CLI on the pinned stack. The signal is that the Fusion and Bronze smoke gates pass and `make upgrade` runs end to end.

## Requirements

Requirements are completed at inception; source is the initiative spec's CAP ids in covers.

## Done when

1. Migration and stack: `v1` exists, and main has no taxi code, `gitops/`, Looker or old workflows. The v1 GCP resources are destroyed and the state bucket is kept. `terraform plan` is clean on 1.16.5 / 8.6.0, with a plan reviewed at each provider step (5 -> 6 -> 7 -> 8.6.0). A grep for `us-east1` finds 0 hits because the region comes from the profile.
2. Config contract: `make validate-config` passes for the demo and `_template` profiles. CI fails on a stale `resolved.yaml`. The Python hash and fingerprint golden vectors pass.
3. Smoke gates, owner-reviewed: Fusion smoke passes (`static_analysis: strict`, column lineage). Bronze smoke passes on Dataproc runtime 3.0 with Iceberg 1.12.0 (create, append, then read from BigQuery). Outcomes of OQ 2, 3 and 5 are recorded.
4. Guardrails: CI fails when a profile has no bytes cap. Budget alerts are set at 50%, 90% and 100% of USD 5. `make teardown` destroys everything. The FR-35 scan fails on a seeded SSN. The marker check fails on an unmarked sample. SM-3 (billing export under USD 5) is measured after E12.
5. Identity and access: the deploy, runtime and dashboard SAs are separate and none has a JSON key. An IAM test shows the runtime SA cannot delete a landing object. The NFR-9 IAM and bucket-policy review appears in the plan.
6. Upgrade and run identity: `make upgrade` runs the platform-upgrade skill end to end on the Terraform 1.15.8 -> 1.16.5 step, and `dependabot.yml` is deleted (E10 delivers the full regression gate). The stub mints a `run_id` and refuses a second concurrent lock.

## Boundaries

The infra and config boundary, owned by one person:
- `infra/` (module pattern and the demo environment)
- `config/` (loader, defaults, demo and `_template`, standards, hash and fingerprint golden vectors, `fingerprint.py`, `lifecycle.yaml`, the D-7 key)
- `versions.yaml`, the Makefile skeleton, the devcontainer
- DDL for the `ops`, `steward` and `mpi_eval` datasets, including `ops.run_events` and `ops.run_lock` with the Dataproc run counter field
- Budget alerts, bytes-cap lint, the FR-35 scanner, the synthetic-marker CI check
- Deploy, runtime and dashboard SAs, and the landing no-delete rule
- `make upgrade` and the deletion of `dependabot.yml`
- Local `make` lint, test and validate-config targets
- The run-identity stub: a minimal `pipeline/` skeleton

Not in scope:
- FR-39 Actions wiring, WIF and the deploy pipeline (E12).
- The FR-40 regression-equality gate (E10 delivers it; E1 stays accountable for CAP-16).
- Per-unit resources: Dataproc and its SA (E3), the model bucket (E6), Cloud Run (E9).
- Writers of `ops.*` beyond the stub: lifecycle (E3), quarantine and drift (E4), run events and lock (E10, which owns `pipeline/` afterwards).
- Per-epic bytes caps, FR-35 clean proofs and Makefile targets, which each later epic adds.
- See the spec's non-goals.

## References

- spec — _bmad-output/initiative-healthcare-dv-platform-upgrade/spec-healthcare-dv-platform-upgrade/spec-healthcare-dv-platform-upgrade.md, CAP-14, CAP-16
- requirements — _bmad-output/initiative-healthcare-dv-platform-upgrade/spec-healthcare-dv-platform-upgrade/requirements-catalog.md, CAP-14, CAP-16, FR-29, FR-35, FR-40, NFR-9, SM-3, D-4, D-7, OQ 2/3/5
- constraint — _bmad-output/initiative-healthcare-dv-platform-upgrade/architecture-healthcare-dv-platform-upgrade/architecture-healthcare-dv-platform-upgrade.md, AD-1
- constraint — _bmad-output/initiative-healthcare-dv-platform-upgrade/architecture-healthcare-dv-platform-upgrade/architecture-healthcare-dv-platform-upgrade.md, AD-3
- constraint — _bmad-output/initiative-healthcare-dv-platform-upgrade/architecture-healthcare-dv-platform-upgrade/architecture-healthcare-dv-platform-upgrade.md, AD-7
- constraint — _bmad-output/initiative-healthcare-dv-platform-upgrade/architecture-healthcare-dv-platform-upgrade/architecture-healthcare-dv-platform-upgrade.md, AD-14
- constraint — _bmad-output/initiative-healthcare-dv-platform-upgrade/architecture-healthcare-dv-platform-upgrade/architecture-healthcare-dv-platform-upgrade.md, AD-16
- constraint — _bmad-output/initiative-healthcare-dv-platform-upgrade/architecture-healthcare-dv-platform-upgrade/architecture-healthcare-dv-platform-upgrade.md, AD-18
- constraint — _bmad-output/initiative-healthcare-dv-platform-upgrade/architecture-healthcare-dv-platform-upgrade/architecture-healthcare-dv-platform-upgrade.md, AD-20
- constraint — _bmad-output/initiative-healthcare-dv-platform-upgrade/architecture-healthcare-dv-platform-upgrade/architecture-healthcare-dv-platform-upgrade.md, AD-24
- skill — .claude/skills/platform-upgrade (driven by `make upgrade`)

## Notes

- Assumption: all data is synthetic for the whole initiative.
- Open question: D-4 region. It is the first story and needs an owner decision. It blocks the first apply.
- Open question: OQ 2, 3 and 5 are settled as smoke-gate outcomes. A failure on OQ 5 or the Fusion gate reshapes E3 and E5.
- Open question: runner contract stability. The stub story sets it and E10 hardens it.
- Unknown: D-7. It ships as a config key with default "unset, report only". E4 waits on it.
- Decision: the user accepted the recommended split and kept E1 whole, with no separate E1a/E1b or CAP-16 epic (2026-10-07).
- Decision: E3 has a whole-epic gate on E1's Bronze smoke story, and the owner reviews any failure before E3 starts (2026-10-07).
- Decision: provider stepping (5 -> 6 -> 7 -> 8.6.0) sits in the migration story, following the architecture, and the Terraform 1.15.8 -> 1.16.5 bump is the first `make upgrade` run (2026-10-07).
- Source conflict: provider stepping owner. The spec puts it in the first FR-40 upgrade and the architecture puts it in migration. It is resolved by the decision above.
- Source conflict: Cosmos is pinned at 1.15.1 in Stack but deferred in the build sequence. Mark it inert in `versions.yaml`.
- Source conflict: `ml_fallback_enabled` is grouped with the cost flags but defaults on. This is consistent with AD-1 and is noted only.
- Source conflict: region. `us-east1` is hardcoded while D-4 makes the region per profile. Done when 1 fixes it.
- Parked: deferred PHI hardening (AD-14, Future Enhancements): tokenization, the restricted dataset, de-identification views, policy tags, audit logs, delete locks and identified extracts.
- Parked: the Gold block on data drift, a follow-up story waiting on the D-7 key that E1 creates.
