# PRD Quality Review — Healthcare Data Vault Platform Upgrade

## Overall verdict
A strong, specific PRD. The thesis is clear: measured MPI quality against known ground truth, built config-first on DV 2.0 + dbt + GCP. It has a solid glossary, real counter-metrics and honest non-goals. The main risks are internal contradictions that downstream workflows will trip over. The "framework for clients" claim and its primary metric (SM-2) sit in Phase 2. The cost and runtime story mixes a free-tier GitHub runner (NFR-8) with mandatory Dataproc full runs (FR-12) and a USD 5 cap that is not tagged as an assumption. The "dbt 2.0" proof point is non-blocking (NFR-7). Several FRs have no testable consequence.

## Decision-readiness — adequate
Decisions are stated as decisions: taxi sunset (§9), Composer and Looker off (§6), and the match-band thresholds (§4.5). The trade-offs in addendum §D are honest. The 11 Open Questions are real, but most of them (Q2, Q3, Q4, Q8, Q11) are architecture choices. Q10 (when to commit the devcontainer changes) is housekeeping and does not belong in a PRD. One `[NOTE FOR PM]` sits at the real tension (FR-29 phasing), but the PRD leaves that tension unresolved.

### Findings
- **high** Framework claim deferred while its primary metric stays primary (§8.2, §10 SM-2, §1 Vision) — The user said this is "a framework I could use for real clients", and the Vision makes config-only onboarding a core claim. But FR-29 and FR-30 are in Phase 2, and SM-2 validates FR-29 and FR-30, so the POC cannot meet a primary metric. *Fix:* move FR-29 and a minimal FR-30 (the Payer C walkthrough) into Phase 1, or demote SM-2 to Phase 2 and say the POC proves config-only onboarding only through FR-8 and FR-9.
- **medium** Open Questions mix product and architecture choices (§11) — Q2, Q3, Q4, Q8 and Q11 belong to the architecture workflow, and Q10 is a git chore. *Fix:* keep only the product-level questions (Q1 cost stance, Q5 public steward deployment, Q7 repo rename) and hand the rest off explicitly to architecture.

## Substance over theater — strong
The personas are justified by the jobs they drive, and two of them have UJs. The NFRs have thresholds (bytes-billed cap, 45 min, USD 5). The Vision is specific to this product. The counter-metrics SM-C1 to SM-C4 are unusually good and clearly not template filler.

### Findings
- **low** "Future client buyer" persona drives no FR beyond NFR-6 (§2.1) — *Fix:* merge it into the Portfolio owner job, or tie it to FR-30's Composer promotion runbook.

## Strategic coherence — adequate
The thesis is clear, and the success metrics validate it (SM-1 measured MPI quality, SM-C3 guards against gaming). The user named three things to prove: DV, dbt 2.0 and GCP. The dbt 2.0 part is weakened by NFR-7, which makes Fusion non-blocking. The cost story also contradicts itself.

### Findings
- **high** Cost and runtime contradictions (§5 NFR-1, NFR-8, §4.3 FR-12, §6) — The user asked to "stay within free tier as much as possible", using GitHub Actions. FR-12 requires Dataproc (no free tier) for full runs. NFR-8 requires the full pipeline to finish on a free GitHub runner. The USD 5 total budget appears as a firm requirement but is not tagged `[ASSUMPTION]`, and the PRD does not trace it to the user. *Fix:* make local Spark on the GitHub runner the default full-run path (free tier). Make Dataproc Spot an opt-in proof run with its own per-run cost cap. Tag the USD 5 figure or attribute it to its source.
- **medium** "dbt 2.0" proof point is non-blocking (§5 NFR-7, §1) — The Vision claims dbt Fusion can build the vault natively, but the PRD accepts Fusion failures. *Fix:* add a success metric such as "Fusion build of Raw Vault + Gold passes on the reference dataset". Keep it non-blocking for CI if needed, but make it a stated POC exit criterion.

## Done-ness clarity — thin
Most FRs have crisp consequences (FR-1, FR-6, FR-13, FR-14, FR-18). Several have none or cannot be tested.

### Findings
- **high** FRs with no testable consequence (§4.7 FR-23, §4.8 FR-25, FR-26, §4.9 FR-28, §4.10 FR-30) — FR-23 says "without scanning all of satellite history" with no bound. FR-25 and FR-26 have no acceptance criteria. FR-28 does not say how "same end state" is checked. FR-30 says "a new engineer follows it" without saying how that is verified. *Fix:* add consequences. For example: a PIT join scans no more than N bytes or only the PIT partitions; the dashboard shows named tiles from named Gold tables; extract stubs produce named files with a fixed schema; a rerun produces identical row counts and hashes, and the skip is logged; a CI job onboards Payer C from config alone.
- **medium** UJ-2 edge case not carried into an FR (§2.3 UJ-2, §4.6 FR-20) — The "two stewards disagree → latest wins, flag for second review" behavior appears in no FR consequence. *Fix:* add it to FR-20.
- **medium** FR-21 retraining has no success bound (§4.6) — It records before and after metrics but has no requirement that metrics do not regress. *Fix:* require that a retrain is promoted only if F1 does not drop and SM-C1 still holds.
- **low** Match-band boundaries leave a gap (§3 Match band, §4.5) — ≥90, <50 and 50–89 leave scores such as 89.5 unassigned. *Fix:* use the ranges [50, 90) and [90, 100].

## Scope honesty — strong
The Non-Goals section does real work. The six assumptions are inline and indexed. The out-of-scope list includes v2 models. With fast path and portfolio stakes, the open-items density (11 OQ + 6 ASSUMPTION + 1 NOTE) is acceptable, but see the decision-readiness finding on OQ triage.

### Findings
- **medium** Untagged numeric targets (§10 SM-1 F1 ≥ 0.97 / 0.90, SM-C1 ≤ 0.5%, SM-7 ≤ 3%, §5 NFR-1 USD 5) — These read as user-confirmed, but they appear to be inferred. *Fix:* tag them `[ASSUMPTION]` and add them to §12.

## Downstream usability — strong
The glossary is thorough and used consistently. FR-1 to FR-30, NFR-1 to NFR-9 and SM-1 to SM-7 / SM-C1 to SM-C4 are contiguous. UJs have named protagonists (Dana, Sam). Cross-references resolve. The addendum separates implementation material cleanly.

### Findings
- **low** "Phase 1: FR-1 to FR-28" conflicts with UJ-1's "realizes" links (§8.1, FR-8, FR-29) — UJ-1 is realized partly by FR-29, which is in Phase 2, so UJ-1 cannot be fully demonstrated in Phase 1. *Fix:* resolve this together with the high finding on phasing.

## Shape fit — strong
This is a single-operator technical capability spec with portfolio and framework intent. Two UJs are the right density. Brownfield references (§9, addendum §F) are specific. The PRD is not over-formalized.

## Mechanical notes
- The Assumptions Index round-trips (6/6), but the untagged targets above should be added.
- `[NOTE FOR PM]` in §8.2 has no index. That is acceptable, but resolve it before finalizing.
- The working title still says "Please confirm". The user confirmed the slug `healthcare-dv-platform-upgrade`, so remove that line.
- Glossary: "Golden key" is defined as `MASTER_MEMBER_HK`, but FR-24 and the Gold section say "member key" for the clustering of `FCT_CLAIMS_MONTHLY`. Clarify whether that means the golden key or the source member HK.
- There is no glossary entry for "Business Vault derivations" versus PIT. This is minor.
- SM-6 needs 30 days of scheduled CI runs, which conflicts with fast-path delivery and free-tier cost. Consider shortening the window or making the metric post-POC.
