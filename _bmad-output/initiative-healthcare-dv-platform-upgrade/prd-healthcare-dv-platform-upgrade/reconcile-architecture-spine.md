# Reconcile: Architecture Spine vs PRD (2026-10-07)

Inputs: spine `architecture-healthcare-dv-platform-upgrade.md` (AD-1..AD-25) + `.memlog.md` (later entries supersede), PRD + addendum after the 2026-10-07 alignment update.
Result: PRD is largely aligned (landing tiering, Bronze per era/WAP/reconcile, fingerprint eras, Fusion blocking, flags-off orchestration, PHI deferral, run lock, Dataproc cap, manual upgrades all reflected). Remaining gaps below. Pure implementation detail (hash normalization rules, WAP branch names, ops column shapes, Stack versions) intentionally left to the spine.

## Contradictions (PRD statement conflicts with spine)

| # | Sev | PRD location | Spine | Issue | Proposed fix |
|---|---|---|---|---|---|
| C1 | High | §3 Steward decision ("match, no match or defer"); FR-20 ("match, no match or defer") | AD-23 decision enum {match, no_match, must_not_link, unmerge}, no defer | Enum differs: PRD has `defer`, spine has `must_not_link` and `unmerge`. FR-18 needs steward reversals (unmerge) | **Needs user**: pick final set. Suggest PRD = match, no match, must-not-link, unmerge (+ defer if wanted, then add to AD-23) |
| C2 | High | §8.3 Out of scope: "effectivity satellites ... Deferred to v2" | AD-13 effectivity satellite on `LINK_PERSON_SAME_AS` (status active/ended); FR-18 itself requires status rows | Out-of-scope line contradicts AD-13 and FR-18 | Reword: "bridges and effectivity satellites beyond the MPI same-as effectivity (FR-18) and what Gold needs" |
| C3 | High | FR-13 member key `payer_id + member_id + person_code`; patient key `facility_id + MRN`; §3 Member | AD-7: member = payer + **subscriber id** + person_code; EMR feeds qualified by **EMR system id** | Key recipes differ (member_id vs subscriber_id; facility vs EMR system) | **Needs user**: confirm recipe; update whichever side is wrong (spine `business_keys.yaml` is authoritative once confirmed) |
| C4 | Med | FR-16 "Score write-back is atomic (staged, then swapped); partial write-back leaves previous results" | AD-13 insert-only per `run_id`; dbt reads only runs with `mpi_complete` event | "Swap" implies replace; spine achieves atomicity via insert-only + completion marker | Reword: "written insert-only per run; consumers read only runs marked complete, so a partial run is invisible" |
| C5 | Med | §3 Canonical schema: "one entity type: claims, eligibility or visits" | AD-8 eight entities (claim, claim_line, eligibility, remittance_835, pharmacy, provider, patient, encounter) | Glossary lists 3, §4.4 lists 8 | Update glossary to the eight entities |
| C6 | Med | FR-1 / FR-37 / addendum D: size params read from `.env` | Determinism convention + AD-1: values in `config/`; `.env` only secrets-free local overrides, `config/` wins | Source of truth inverted | Say size params are in client config (`volume_profile`), overridable locally via `.env` |
| C7 | Med | FR-30 placed in Phase 2 (§8.2), but its consequence "CI job onboards Payer C ... zero diff outside config/" | Spine CI guards: Payer C zero-diff in `pr-validate.yml` (Phase 1); SM-2 measured in Phase 1 | Phase split blurred: CI check is Phase 1, guide is Phase 2 | Move the Payer C CI job into FR-29 / SM-2 consequence (Phase 1); leave only the guide in FR-30 |
| C8 | Low | FR-29 "dataset prefixes" | AD-19 + conventions: one project per client, fixed dataset names (`silver`, `raw_vault`, ...) | No prefixes exist | Drop "dataset prefixes" from FR-29 |
| C9 | Low | FR-21 promotion "F1 does not drop and false-merge meets SM-C1" | AD-13 "promoted only if it beats the current one on AD-25 held-out metrics" | Non-regression vs strictly-better | Align wording (suggest PRD rule; update AD-13 to "no F1 drop and SM-C1 met") |
| C10 | Low | FR-24/FR-25/§3 `DIM_PATIENTS`, `DIM_VISITS` | AD-13 `DIM_PATIENT`; convention `DIM_<X>` | Plural vs singular | Pick one (singular per spine convention) |

## Spine decisions not reflected in PRD (capability/constraint level)

| # | Sev | Spine | Missing in PRD | Proposed PRD change |
|---|---|---|---|---|
| G1 | Med | AD-25 MPI eval: ground truth in `mpi_eval`, never readable as a feature; model artifacts versioned | FR-19/FR-17 do not state ground truth is excluded from features or that models are versioned/retained for rollback | Add FR-17 consequence: ground truth is never a model feature; each model version is retained so the previous one can stay active |
| G2 | Low | AD-23 decision row has no scores; FR-20 wants "model scores shown at decision time" | Spine gap rather than PRD; note for spine (`steward.decision` link to `candidate_id`) | Spine update, not PRD |
| G3 | Low | AD-16 Dataproc: TTL + run counter; no per-run cost ceiling | FR-12 "per-run cost ceiling in configuration" not realized in spine | Spine update (config key + runner check) or drop from FR-12 |
| G4 | Low | FR-18 split survivorship ("part with oldest record keeps key") | AD-13 covers merge only | Spine update |
| G5 | Low | AD-3 duplicate by content hash regardless of name | Already in FR-5 | none |

## No action needed
Landing tiering/no delete, Bronze WAP + reconcile + no expiration, fingerprint/additive eras, unmapped replay, quarantine precedence, drift blocking only with thresholds, Fusion-only build, flags-off orchestrators, run lock, run-id minting, Dataproc 10-run cap, PHI deferral, WIF/CLI-first, one project per client, manual upgrade skill, Python 3.12, migration/v1 branch.
