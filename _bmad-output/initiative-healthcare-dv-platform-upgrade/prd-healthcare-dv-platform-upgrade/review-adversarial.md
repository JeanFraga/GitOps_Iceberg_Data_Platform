---
title: Adversarial Review — Healthcare DV Platform Upgrade PRD
reviewer: skeptical data architect (adversarial lens)
date: 2026-10-07
inputs: prd-healthcare-dv-platform-upgrade.md, addendum.md
---

# Adversarial Review

## Verdict
**Revise before architecture.** The vision fits a portfolio-plus-framework POC and the scope is reasonable. But the MPI metrics are defined loosely enough that the headline result ("measured identity resolution") can't be checked as written. The landing-zone immutability requirement can't be built on GCS as specified. The cost and runtime NFRs contradict each other. None of these needs a redesign. Each needs a tighter definition or a decision.

## Findings (most severe first)

### C1 — CRITICAL: MPI thresholds and success metrics are incoherent and partly unmeasurable
- **Band gap:** auto-match is ≥90%, edge is 50–89%, new key is <50%. That leaves scores in [89, 90) unassigned (§3, §4.5). Define the bands as half-open intervals: `[0,0.5) / [0.5,0.9) / [0.9,1]`.
- **"%" of what:** Splink produces a match weight and a `match_probability`. With EM-trained m/u and a prior λ that it estimates itself, the probability is poorly calibrated, so fixed cutoffs at 0.5 and 0.9 are arbitrary. Say whether thresholds apply to the probability or to the weight, and require calibration (or threshold selection against a held-out ground-truth slice).
- **Undefined denominators:** SM-1 (F1 ≥0.97, edge F1 ≥0.90), SM-7 (≤3% of candidate pairs queued), SM-C1 (≤0.5% false merges) and FR-4 ("~2% of candidate pairs are edge cases") don't say whether they are pairwise or cluster-level, or whether they count before or after blocking. Candidate pairs after blocking are mostly non-matches. So "2% edge" and "≤3% queued" are trivially satisfied or meaningless, depending on the blocking rules, and they can be gamed by changing the blocking. Pick pairwise metrics over **true-match pairs and blocked pairs**, plus cluster metrics (B-cubed or pairwise-after-closure), and state both.
- **Transitivity vs false merges:** FR-18 forces transitive closure. One bad edge (for example, twins at a shared address) collapses clusters, so SM-C1 can fail even when pairwise precision is high. The PRD needs a rule for cluster conflicts (max cluster size, a must-not-link from steward "no match" that blocks closure).
- **Circularity:** the generator's noise model and the matcher are written by the same author, so F1 ≥0.97 mostly measures how closely the matcher fits the generator. Require a held-out noise scenario or seed that the model never sees during tuning, or the portfolio claim is weak.
- **ML fallback training data:** FR-17 needs labels before any steward decisions exist. Say whether it trains on ground truth (leakage into the evaluation) or is bootstrapped. Train/test split by true person ID is required.

### H1 — HIGH: The immutable landing zone (FR-5) is not implementable as written on GCS
- A GCS bucket **retention policy** blocks overwriting or deleting objects. A same-name upload is *rejected*. It does not create a new version, and GCS does not allow object versioning and a retention policy on the same bucket. FR-5's two consequences contradict each other. Choose (a) versioning with a soft-delete policy (no hard immutability), or (b) a retention policy with unique, content-addressed object names.
- If the retention policy is **locked**, the "delete GCP resources / idle $0 / teardown" goals (§8.1, NFR-1) can't be met until objects expire, and the lock can't be undone. The PRD should forbid locking in the POC.

### H2 — HIGH: Cost and runtime NFRs contradict each other
- FR-12 says full runs use Dataproc. NFR-8 says the full pipeline runs on a free GitHub runner in under 45 minutes. SM-6 requires a **scheduled** end-to-end run with ≥95% success over 30 days. If those scheduled runs use Dataproc Serverless, the billing minimums apply (at least 1 minute, with the default about 12 DCU across driver and executors, plus shuffle storage). At roughly $0.15–0.30 per run, a daily schedule costs about $5–9 in a month, which **exceeds the entire POC budget** (NFR-1, SM-3). Spot pricing doesn't apply to Serverless standard tier, as the addendum §D wording ("Spot/preemptible ... Serverless") suggests it does. Decide which: scheduled runs are local-Spark only and Dataproc runs are manual and capped (N runs), or the budget goes up.
- BigQuery storage: about 2 GB of compressed CSV expands roughly 5–10× in BigQuery and is then copied into Silver, the vault, PIT and Gold. On top of that, time-travel and fail-safe storage keep 7+7 days of every rewritten table, and idempotency tests deliberately rerun loads. The 10 GiB free storage is at risk. The cost is cents, but "idle ≈ $0" needs a teardown or a dataset expiration step. Add a storage budget per layer.
- `maximum_bytes_billed` only works if every engine sets it. The Splink extract, the Spark BigQuery connector reads and the Looker Studio queries ignore the dbt profile. List each enforcement point.
- Budget alerts don't stop spend. Add a budget-triggered kill switch (a Pub/Sub budget topic that disables billing or deletes Dataproc), or downgrade the claim to "alert".

### H3 — HIGH: dbt Fusion and the DV package path are an unproven critical dependency
- "dbt 2.0" isn't a released product name. Fusion is a separate engine (the Rust-based CLI, licensed differently from Core), and its BigQuery adapter coverage and package compatibility are still moving. NFR-7 handles this correctly (Core blocking, Fusion non-blocking). But the §1 vision promises that Fusion "can build the vault natively". Either soften the vision or make the Fusion build a measured outcome (a pass/fail matrix per model).
- FR-15 requires a DV package **and** in-house macros that are "behaviorally equivalent" and give identical hash keys. That doubles the vault work on a fast-path POC. Packages differ in hash input normalization, null sentinels, delimiters, hashdiff column ordering and ghost records, so identical keys are a project of their own. Recommend in-house macros only (they are small, Fusion-safe and portable), with the package as an optional spike, or the package only.
- The Cosmos and Fusion interaction is untested. Cosmos parses `manifest.json`, and Fusion's manifest and log formats differ. Keep `BashOperator` as the primary fallback for the Fusion track.
- Open Q8 (the hash standard) blocks FR-13 and FR-15. Decide it now: MD5 or SHA-256 as hex STRING or BYTES are portable. FARM_FINGERPRINT is BigQuery-only and conflicts with the "framework for clients" claim.

### M1 — MEDIUM: Iceberg / native BigQuery / tiering contradictions
- The addendum §A (the user's architecture, verbatim) specifies Coldline/Archive 1:1 retention, "external/Iceberg" Bronze, "STRING/VARIANT" and "partitioned by _FILE_NAME & _INGESTED_AT". The PRD quietly defers Iceberg and archive tiers to Phase 2 or documentation only (FR-5, Open Q1), while §9 conflict 2 has already decided "native BigQuery Silver" — Open Q1 is presented as still open. Record the decision explicitly. The repo is literally named *GitOps_Iceberg*, so dropping Iceberg from the POC is a portfolio-narrative choice that the user should confirm.
- BigQuery has no VARIANT type (JSON is the analogue). `_FILE_NAME` is a pseudo-column and can't be a partition key. External tables are hive-partitioned on a path key (`ingest_date`). Fix the wording so the architecture workflow doesn't inherit it.
- FR-6 says Bronze rows equal source records. For FHIR NDJSON (nested) and EDI-derived JSONL, "every column is a string" isn't well defined. Specify one JSON string column per record, or flattening rules.

### M2 — MEDIUM: Composer-portability claims are overstated
- The addendum §D picks Airflow 3.x locally. Composer 3 images lag behind upstream Airflow, and provider versions are fixed by the image. "Same DAG files without rewrite" needs a pinned Airflow and provider version that matches a real Composer image, plus a CI job that tests against that constraint set.
- FR-27 says "Composer-specific operators only behind the runtime switch", which admits that the DAG code branches. Define the abstraction (a task factory per runtime) and test both branches with DagBag at least.
- `dag.test()` in GitHub Actions runs Spark, dbt and Splink in one process on a 7 GB runner. Memory and the 45-minute budget (NFR-8) are unverified for about 50k members, a few million claim lines and Splink EM. Add a "CI volume" profile that is distinct from the "default volume".

### M3 — MEDIUM: Missing failure modes
- **Steward reversals vs insert-only DV:** FR-18 and FR-20 need golden-key splits and un-merges over time, which is effectivity-satellite or status-tracking semantics. But §8.3 defers effectivity satellites to v2. Specify how a reversal is represented in `LINK_MEMBER_SAME_AS` and `SAT_MPI_MATCH_DETAILS`.
- **Golden-key stability:** FR-18 says keys are "stable unless new evidence ...". There is no survivorship rule for which key survives when two clusters merge, or which one is reissued on a split.
- **Late or out-of-order files and backfills:** the effect on satellite load dates, PIT rebuilds and FR-28 state markers isn't defined.
- **Partial load-back:** if the Splink or DuckDB scores are written back to BigQuery only partially, there is no atomicity requirement (stage, then swap).
- **Quarantine re-processing:** FR-9 quarantines a file, but there is no requirement for replaying it after a mapping fix.
- **Steward identity:** a local or Community Cloud Streamlit app has no authentication, so FR-20's "steward identity" is unverifiable. NFR-4 also forbids PHI-like data in a public UI, and synthetic names still look like PHI. Decide: no public deployment.
- **Concurrent runs:** two Actions runs on the same period would race the FR-28 markers. Require a concurrency group or lock.

### M4 — MEDIUM: Scope and phasing undercut the fast path
- Phase 1 contains FR-1 to FR-28, which includes the steward UI, the retraining loop, the ML fallback, PIT, an OBT, two DV paths and extract stubs. That isn't a fast path. Suggest an MVP cut: FR-1–14, 16, 18, 19, 22, 24, 27, with FR-17, 20, 21 and 15 as fast-follow.
- SM-2 (config-only onboarding) validates FR-29 and FR-30, which are Phase 2. So the main "framework" success metric can't be measured in Phase 1. Either pull FR-29 in (the PRD's own note recommends it) or move SM-2.

### L1 — LOW: Requirements that can't be measured or verified
- FR-1 asks for byte-identical Spark output "apart from timestamps". Spark part-file names, ordering and partition counts aren't deterministic. Restate it as a content-hash equality of sorted records.
- FR-23 says "without scanning all of satellite history", with no measurable criterion (for example, bytes scanned ≤ X% of the satellite).
- NFR-4 says "no PHI in logs", with no check. Add a CI log scan for the generator's name and SSN patterns.
- "Realistic" (§4.1) and SM-C3's "about 2%" have no tolerance. Give a ± band.
- SM-6 requires 30 days of scheduled runs, which conflicts with H2 and isn't reachable before the POC is "done".
- Addendum §E figures are tagged unverified, and BQML at "$312.50/TB" is presented as a cost driver without a volume estimate. Local XGBoost avoids this entirely, so close Open Q4 in favour of local XGBoost.

## Recommended decisions to close before architecture
1. MPI: score type, half-open bands, metric definitions (pairwise and cluster, with denominators), a held-out evaluation seed, and a must-not-link rule.
2. Landing: versioning *or* retention with unique names. No bucket lock.
3. Cost: scheduled E2E runs on local Spark only, a capped number of Dataproc runs, and a budget kill switch.
4. Vault: in-house hash macros as the primary path. MD5 or SHA-256. Package as a spike.
5. Iceberg: an explicit POC yes or no, recorded as a decision rather than an open question.
6. Phase 1 MVP cut, and FR-29 pulled in, or SM-2 moved.
