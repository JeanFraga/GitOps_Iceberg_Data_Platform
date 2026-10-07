# Reconcile: PRD -> Architecture Spine

Input: `prd-healthcare-dv-platform-upgrade.md`. Spine: `architecture-healthcare-dv-platform-upgrade.md`. Authority: `.memlog.md` (later wins).
Date: 2026-10-07.

## A. Upstream PRD update needed (deliberate user overrides, not spine defects)

| # | PRD text | Spine / memlog decision |
|---|---|---|
| U-1 | NFR-7, SM-8, §1, FR-15: dbt Core blocking, Fusion non-blocking; Fusion via BashOperator not Cosmos | AD-15 Fusion blocking, Core local fallback; Cosmos 1.15.1 in stack |
| U-2 | FR-5: 7-day unlocked retention; tiers documented, not exercised; §6 "Archive/Coldline documented, not exercised" | AD-3 Coldline 7d -> Archive 60d, never deleted |
| U-3 | §1, §4.9, FR-27, NFR-6, §8.1 "local Airflow", FR-38 "DAG upload": every step an Airflow task; CI DAG tests vs Composer constraints | AD-17 DAG_SPEC + local runner default; Airflow/Composer flag-off |
| U-4 | FR-12/D-2: runtime unspecified; NFR-8 | AD-21 Dataproc Serverless 3.0 (Spark 4.0, Py 3.12) |
| U-5 | FR-6: Bronze partitioned by ingestion date, new column = Iceberg schema evolution | AD-4 one table per (source, feed, era) |
| U-6 | FR-9, glossary "Schema era: date-bounded" | AD-5 era = schema fingerprint (memlog: user "b") |
| U-7 | Glossary golden key `MASTER_MEMBER_HK`, `LINK_MEMBER_SAME_AS`, FR-18 "every member record" | AD-13 `golden_person_hk`, HUB_PERSON, member+patient links |
| U-8 | Glossary canonical schema = claims, eligibility, visits | AD-8 seven entities |
| U-9 | §4.7 LINK_VISIT_CLAIM in Raw Vault list (§4.4) | AD-12 BV derivation |
| U-10 | §6 "Composer kept as reference module" / Looker | AD-16 consistent; Looker scrapped (fine) |

## B. Contradictions needing a decision (not covered by an override)

1. **UJ-1 edge case vs AD-5/AD-9 (high).** PRD: a file with a new column stays in Bronze, is reported as drift, Silver loads padded, run does not fail. Spine: new fingerprint -> `unmapped_<fp8>` -> quarantined at Silver until mapping added. Also FR-3 "new columns mid-era" drift scenario and SM-4 rely on detection, while SM-C2 counterbalances quarantine growth. Decide: does an additive-only fingerprint change auto-map to the parent era (pad + drift row) or quarantine? Fix: add an "additive drift tolerance" rule to AD-5/AD-9, or record the override and update UJ-1.
2. **Data drift blocking (medium).** FR-36 "data drift is reported, never blocking by itself"; NFR-5 "drift thresholds block promotion to Gold"; AD-9 "blocks at Gold publish". PRD is self-contradictory; spine chose NFR-5. Needs user confirm, then PRD fix. Also D-7 thresholds deferred while a blocking gate depends on them: define behavior with no thresholds configured (default warn).
3. **Bronze expiration vs system of record (medium).** NFR-1: "Bronze has a default table expiration"; FR-34 default expiration on non-landing datasets + teardown target. AD-3/AD-4 make Bronze the queryable system of record, landing never deleted (Archive has 365-day minimum storage; teardown deletes incur early-deletion charges). Spine has no expiration or teardown rule. Decide expiration scope and teardown cost under the USD 5 budget.
4. **Retention policy dropped (low/medium).** FR-5 requires an unlocked GCS retention policy (no delete inside window) and notes versioning conflicts. AD-3 enforces immutability only via naming + "overwrite rejected" (mechanism unstated: precondition `ifGenerationMatch=0`? IAM without delete?). Specify the mechanism.
5. **Least-privilege SA per stage (medium).** NFR-9 "least-privilege service accounts for each stage"; AD-18 one runtime SA + deploy SA; AD-14 restricts Bronze to "the runtime SA". Decide one vs per-stage SAs (ingestion, dbt, MPI, dashboard, steward).
6. **PHI controls weaker than NFR-4 (high).** Spine has `restricted_phi` dataset + HMAC views, but no BigQuery policy tags / column-level security / dynamic data masking, no named-role dataset access, no Safe Harbor rules (18 identifiers, ZIP3 with 000 low-pop, dates to year, age 90+ cap). PHI also lives in Silver (patient, eligibility) and Raw Vault demographics sats; spine only says "PHI columns live in restricted_phi" - unclear how Silver/Raw Vault comply. FR-14 `SAT_MEMBER_SENSITIVE` (SSN) has no home in ER.
7. **Vault model drift vs §4.4 (high).** PRD names that are missing or renamed in spine ER with no memlog decision: `HUB_CLAIM_LINE`, `LINK_CLAIM_LINE` (spine: `SAT_CLAIM_LINES` on HUB_CLAIM), `HUB_PHARMACY_CLAIM`/`LINK_MEMBER_PHARMACY_CLAIM`/`SAT_PHARMACY_CLAIM` (spine: `HUB_RX_CLAIM`, `SAT_PHARMACY`, no member link -> FR-33), `SAT_COVERAGE` (spine `SAT_ELIGIBILITY`), `SAT_CLAIM_HEADER`, `SAT_CLAIM_ADJUDICATION` (835 has a canonical Silver entity but no vault target -> FR-22 adjudication flags unsourced), `SAT_MEMBER_SENSITIVE`, `PIT_MEMBER_CLAIMS` (spine `PIT_PERSON_CLAIMS`), `DIM_PATIENTS` (spine `DIM_PATIENT`). FR-32 provider linked to encounters: no `LINK_VISIT_PROVIDER`. Either reconcile ER to PRD or log decisions.
8. **MPI write-back atomicity (low).** FR-16 staged-then-swapped write-back; AD-13 insert-only per run_id. Compatible only if readers select the latest committed run_id - state the "current run" pointer rule.
9. **Terraform version (low).** Spine stack Terraform 1.16.5; latest commit d581efa standardised CI/devcontainer on 1.15.8. Note as upgrade step.

## C. Requirements with no home in the spine

| PRD item | Gap |
|---|---|
| FR-1/NFR-2/SM-5 determinism | No rule on seeds (training vs evaluation seed disjoint), record-sorted SHA-256 equality, `.env` size config vs AD-1 "everything in config/" (`.env` is a second contract) |
| FR-1/FR-12 full-size generation on Dataproc | Container view puts datagen only in dev container; no Spark-backed datagen path |
| FR-3/FR-36 generator manifest | No location/shape for manifest; drift detection tests (SM-4) unhomed |
| FR-4 ground truth table | No dataset/table; who may read it (eval must not leak into training) |
| FR-7 EDI pre-parse | No component or table for derived line representation; Bronze `_raw_line` only partially covers |
| FR-6 snapshot tagged with run ID, rollback | Not stated |
| FR-12 Dataproc TTL/auto-delete guard, per-run cost ceiling, run counter (max 10) | AD-16 states cap but no enforcement mechanism |
| FR-16 blocking recall, model version per pair; FR-19 metrics table + CI summary | No metrics table (`ops`? `mpi_metrics`?) |
| FR-17 ML on/off flag; person-split training | Flag not in conventions; no model artifact store / registry |
| FR-18 max cluster size flag, split survivorship, status rows | Partial in AD-13 |
| FR-20 second-review flag, scores-at-decision; dedupe "unless inputs change" | Steward table shape unstated; local app writing BigQuery `steward` needs credentials story |
| FR-21 retrain promotion gate (F1 non-drop + SM-C1) | No home |
| FR-23 PIT 20% bytes bound, PIT partitioning | Not stated |
| FR-24/FR-2 reference data (ICD-10, HCPCS public files, NDC 11-digit normalization, DRG/rev codes) | No seeds/reference location; licensing guard (no CPT/CDT/NCQA) absent |
| FR-26 HEDIS/payer extract stubs, FR-31 continuous-enrollment check | No directory or writer |
| FR-28 serialize runs per client+period (lock) | Only "no CLI apply during deploy"; pipeline-level lock unhomed |
| FR-29 two profiles (demo + template), CI validates both | Spine mentions demo only |
| FR-30/SM-2 Payer C CI job with zero diff outside config/; SM-C4 per-source branch count = 0 | No CI check |
| FR-34 CI fails if dbt profile/job lacks cap; enumerated enforcement points; budget alert at 50/90/100% | AD-16 asserts caps but no list or CI check |
| FR-37/SM-9 CI repo-weight check | Missing |
| §6 CI guard: every landed file has synthetic marker; NFR-4 "synthetic data, no real PHI" on every artifact | Missing |
| FR-38 path-filtered deploy, manual dispatch, deploy concurrency group; NFR-10/SM-10 15-min | AD-18 partial |
| FR-39 plan posted to PR, dashboard build | Partial |
| SM-6 scheduled e2e CI run | No schedule exists with Airflow/Workflows off; define a scheduled GHA invoking the local runner |
| NFR-8 45-min CI volume on 7GB runner | Not stated; Splink/DuckDB backend (D-1) not explicitly decided |
| D-4 region | Not resolved in spine; needed before first apply |
| D-5 Composer image | Pinned in stack (ok) |

## D. Phasing / migration not carried

- §8.1/§9: taxi code to `v1` branch; delete taxi datasets/GCP resources; drop Argo CD; replace `composer-sync.yml`, `release.yml`, `terraform.yml`; delete dependabot.yml; provider ~>5 -> 8.x step upgrade (memlog). Spine has no migration/teardown section - add a Deferred or "Migration" row so ticketing picks it up.
- Phase 1 "no MVP cut" and "move fast" tone: spine silent; fine but tickets need the order.
- D-10 devcontainer commit housekeeping: not architectural.

## E. Quiet constraints check

- Budget USD 5: AD-16 covers posture; Coldline/Archive minimum durations and Bronze Iceberg storage not costed (B-3).
- Reproducibility: pinning covered (AD-20); data determinism not (C).
- PHI: partially (B-6).
- Tone/portfolio: "illustrative, not certified" labels on extracts and X12 absent.
