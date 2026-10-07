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

The taxi platform is preserved on `v1` and removed from main (GCP resources destroyed outside the loop), and the demo project is rebuilt from the CLI on Terraform 1.16.5 with Google providers 8.6.0. The config contract (FR-29) and its golden vectors exist, the cost and PHI guardrails are enforced before the first BigQuery spend, a run-identity stub mints `run_id` and takes the run lock, and `make upgrade` is the only upgrade path. Every later epic builds on this baseline. See the initiative spec, CAP-14 and CAP-16, plus FR-29, FR-35, FR-40, NFR-9 and SM-3 in the requirements catalog.

## Outcome

The platform owner can apply, guard and upgrade the demo project from the CLI on the pinned stack. The signal is that `terraform plan` is clean on 1.16.5 / 8.6.0 in us-east1 and `make upgrade` runs end to end.

## Requirements

- CAP-14: Every BigQuery-querying engine is capped, cost-bearing services are flagged off, spend is alerted at 50%, 90% and 100%, and logs are scanned for PHI-shaped values; here also the migration, config contract, identity and run-identity baseline the guardrails stand on. (spec, CAP-14; FR-29, FR-35, NFR-9, D-4, D-7)
- CAP-16: Pinned dependencies are upgraded on demand through the platform-upgrade skill via `make upgrade`, and Dependabot is removed; E10 delivers the full regression gate. (spec, CAP-16; FR-40, SM-3)

## Done when

1. Migration and stack: `v1` exists. Main has no taxi code, `gitops/`, Looker or old workflows. A check confirms that no v1 GCP resources remain and the state bucket is kept (they are destroyed outside the loop). `terraform plan` is clean on 1.16.5 / 8.6.0, with a plan reviewed at each provider step (5 -> 6 -> 7 -> 8.6.0). The region comes from the demo profile (us-east1), and a grep for `us-east1` under infra/ finds 0 hits.
2. Config contract: `make validate-config` passes for the demo and `_template` profiles. The stale-`resolved.yaml` check (a make target CI can call) fails on a hand-edited file. The Python hash and fingerprint golden vectors pass, and `lifecycle.yaml` and the D-7 key validate.
3. Guardrails: the bytes-cap lint fails when a profile has no cap. Budget alerts are set at 50%, 90% and 100% of USD 5. `make teardown` destroys everything except the state bucket. The FR-35 scan fails on a seeded SSN. The marker check fails on an unmarked sample. SM-3 (billing export under USD 5) is measured after E12.
4. Identity and access: the deploy, runtime and dashboard SAs are separate and none has a JSON key. An IAM test shows the runtime SA cannot delete a landing object. The NFR-9 IAM and bucket-policy review appears in the plan. The ops, steward and mpi_eval DDL, the warehouse bucket and the catalog are applied.
5. Upgrade and run identity: `make upgrade` runs the platform-upgrade skill end to end on the Terraform 1.15.8 -> 1.16.5 step, and `dependabot.yml` is deleted (E10 delivers the full regression gate). The stub mints a `run_id` and refuses a second concurrent lock.

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
- requirements — _bmad-output/initiative-healthcare-dv-platform-upgrade/spec-healthcare-dv-platform-upgrade/requirements-catalog.md, CAP-14, CAP-16, FR-29, FR-35, FR-40, NFR-9, SM-3, D-4, D-7, OQ 2/3/5 (risk moved to E3/E5)
- constraint — _bmad-output/initiative-healthcare-dv-platform-upgrade/architecture-healthcare-dv-platform-upgrade/architecture-healthcare-dv-platform-upgrade.md, AD-19
- constraint — _bmad-output/initiative-healthcare-dv-platform-upgrade/architecture-healthcare-dv-platform-upgrade/architecture-healthcare-dv-platform-upgrade.md, Migration from the current repo
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
- Open question: runner contract stability. The stub story sets it and E10 hardens it.
- Unknown: D-7. It ships as a config key with default "unset, report only". E4 waits on it.
- Decision: the user accepted the recommended split and kept E1 whole, with no separate E1a/E1b or CAP-16 epic (2026-10-07).
- Decision: the E3 whole-epic gate on E1 is dropped along with the Bronze smoke. E3 entries pin 1.4, 1.6, 1.7 and 1.10 instead (2026-10-07).
- Decision: provider stepping (5 -> 6 -> 7 -> 8.6.0) sits in the migration story, following the architecture, and the Terraform 1.15.8 -> 1.16.5 bump is the first `make upgrade` run (2026-10-07).
- Source conflict: provider stepping owner. The spec puts it in the first FR-40 upgrade and the architecture puts it in migration. It is resolved by the decision above.
- Source conflict: Cosmos is pinned at 1.15.1 in Stack but deferred in the build sequence. Mark it inert in `versions.yaml`.
- Source conflict: `ml_fallback_enabled` is grouped with the cost flags but defaults on. This is consistent with AD-1 and is noted only.
- Source conflict: region. `us-east1` is hardcoded while D-4 makes the region per profile. fixed by story 1 and Done when 1.
- Parked: deferred PHI hardening (AD-14, Future Enhancements): tokenization, the restricted dataset, de-identification views, policy tags, audit logs, delete locks and identified extracts.
- Parked: the Gold block on data drift, a follow-up story waiting on the D-7 key that E1 creates.
- Decision: D-4 region = us-east1, the region closest to the owner in Miami. It is set in the demo profile, there is no region decision story, and no resource hardcodes it (2026-10-07).
- Decision: there are no Fusion or Bronze smoke gates. In the user's words, "bigquery is fully supported by dbt 2.0, let's assume it works, loop will deal with this". The OQ 2, 3 and 5 risk moves to a note on the first E3 story (Bronze) and the first E5 story (Fusion) (2026-10-07).
- Decision: the user and assistant destroy the taxi GCP resources outside the loop (v1 pushed from a5f3931). Story 1 removes the taxi code from main and only verifies that the resources are gone. The state bucket is kept (2026-10-07).
- Decision: the breakdown runs under bmad-build-auto. plan_checkpoint is set on the high-risk entries (migration, provider stepping, IAM/SA, datasets, upgrade), and there is no done_checkpoint because hitl covers the person steps (2026-10-07).
- Decision: Makefile target appends by entries 3, 8, 9, 10 and 11 are accepted as parallel append-only edits to the skeleton entry 5 owns (2026-10-07).
- Decision: the user approved the story set ("Stories look good"), so entries 1 and 7 stay whole rather than split (2026-10-07).
- Decision: the epic runs fully unattended under bmad-build-auto: no story needs a person, no plan checkpoints, and the builder runs every CLI apply and gcloud change itself (`terraform apply -auto-approve`, `gcloud --quiet`); budget alerts are created with the owner's credentials, with no billing role granted to a service account. User's words: "Use cli commands that can auto approve" (2026-10-07).
