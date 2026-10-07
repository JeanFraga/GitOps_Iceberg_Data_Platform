---
type: epic
title: "Steward review UI"
parent: initiative-healthcare-dv-platform-upgrade
covers: [CAP-9]
after: []
assignee: ""
risk: medium
---

# Steward review UI

## Description

A local Streamlit app lets a data steward list and view queued MPI pairs with their context and record one of five decisions (match, no match, must-not-link, unmerge, defer) with a reason, writing insert-only audited rows to `steward.decision`. Those decisions feed E6's retrain gate, so steward judgement becomes training labels without letting a worse model through. The intent is CAP-9 in the initiative spec; the requirement lines are FR-20, FR-21 and UJ-2 in the requirements catalog.

## Outcome

Data stewards can resolve uncertain identity pairs with full audit, and the decisions stick and feed retraining; UJ-2 (the 0.72 twins pair) passing end to end shows it worked.

## Requirements

Requirements are completed at inception; source is the initiative spec's CAP ids in covers.

## Done when

1. All five decision types store who (local OS identity), when, why and the scores shown; a decided pair is not requeued unless its inputs change, and a no-match never auto-matches again.
2. A conflicting decision makes the latest win, keeps both in the audit and flags the pair for second review.
3. Handoff: E6's retrain gate consumes E7 decisions, and a retrain that would be worse is refused (shown through E6).
4. UJ-2 is scripted and passes end to end, including the disagreement edge case; the FR-35 scan is clean over the UI logs, with a canary seeded.
5. Runs against the demo client project from the CLI (`make <target>` with the demo profile), with output in the demo project's GCP datasets, and passes inside `make e2e-chain` at CI volume on the samples with the epics downstream still passing.

## Boundaries

Follows the capability boundary: `steward_ui/`, which writes `steward.decision` only. Not in scope: the review queue, scoring, applying decisions to golden keys and the retrain gate (E6); `steward` DDL (E1); the PHI scanner itself (E1). The app is local-only. PHI hardening is out of scope (see the spec's Non-goals).

## References

- parent — /workspaces/GitOps_Iceberg_Data_Platform/_bmad-output/initiative-healthcare-dv-platform-upgrade/initiative-healthcare-dv-platform-upgrade.md
- spec — /workspaces/GitOps_Iceberg_Data_Platform/_bmad-output/initiative-healthcare-dv-platform-upgrade/spec-healthcare-dv-platform-upgrade/spec-healthcare-dv-platform-upgrade.md, Capabilities (CAP-9)
- spec — /workspaces/GitOps_Iceberg_Data_Platform/_bmad-output/initiative-healthcare-dv-platform-upgrade/spec-healthcare-dv-platform-upgrade/requirements-catalog.md, CAP-9 (FR-20, FR-21, UJ-2), FR-35, SM-7, SM-C1
- constraint — /workspaces/GitOps_Iceberg_Data_Platform/_bmad-output/initiative-healthcare-dv-platform-upgrade/architecture-healthcare-dv-platform-upgrade/architecture-healthcare-dv-platform-upgrade.md, AD-1
- constraint — /workspaces/GitOps_Iceberg_Data_Platform/_bmad-output/initiative-healthcare-dv-platform-upgrade/architecture-healthcare-dv-platform-upgrade/architecture-healthcare-dv-platform-upgrade.md, AD-2
- constraint — /workspaces/GitOps_Iceberg_Data_Platform/_bmad-output/initiative-healthcare-dv-platform-upgrade/architecture-healthcare-dv-platform-upgrade/architecture-healthcare-dv-platform-upgrade.md, AD-13
- constraint — /workspaces/GitOps_Iceberg_Data_Platform/_bmad-output/initiative-healthcare-dv-platform-upgrade/architecture-healthcare-dv-platform-upgrade/architecture-healthcare-dv-platform-upgrade.md, AD-23
- input — /workspaces/GitOps_Iceberg_Data_Platform/_bmad-output/initiative-healthcare-dv-platform-upgrade/tickets.toml, [[epic]] id 7 (needs from E6)

## Notes

- Waits on epic-mpi because: the UI reads the `steward.review_queue` schema, match candidates and scores, and the handoff check runs through E6's eval harness and retrain gate (story-level needs in tickets.toml, not a whole-epic gate).
- Decision: 2026-10-07 — user accepted the recommended split; E6 and E7 stay separate, with the retrain gate in E6 consuming E7's `steward.decision` rows. Merge only if one person builds both.
- Parked: deferred PHI hardening under AD-14 (tokenization, restricted dataset, de-identification views, policy tags, audit logs); all data is synthetic.
