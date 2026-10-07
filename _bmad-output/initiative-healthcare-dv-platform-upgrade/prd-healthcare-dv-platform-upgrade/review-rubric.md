# PRD Quality Review — Healthcare Data Vault Platform Upgrade

## Overall verdict
This is a strong, decision-dense PRD: the thesis (DV 2.0 + dbt Fusion + a *measured* MPI on synthetic ground truth, for under USD 5) is explicit, FRs carry testable consequences, counter-metrics are real, and the 2026-10-07 alignment with the architecture spine left no open product questions. The risks are narrow but real: a train/evaluation leakage path through steward decisions undermines the headline SM-1 metric, the USD 5 budget has no per-component cost model behind it, and a few phase/ownership seams (Payer C onboarding, Actions-measured SM-10 vs CLI-first loop) need a sentence each.

## Decision-readiness — strong
Decisions are stated as decisions and marked "(decided)" / "(confirmed)": no MVP cut (§8.1), Iceberg only at Bronze (FR-6, §8.3), MD5 hex hashing (FR-13), local XGBoost (FR-17), local-only steward UI (FR-20), CLI-first loop (§4.12), Dependabot removal (FR-40). Trade-offs name what is given up (e.g. FR-6 "because the dbt Fusion engine has no native Iceberg support"; FR-15 package spike "not required to be zero"). §11 closes 13 questions and the deferred table D-1..D-10 has owners and revisit triggers, which is exactly right. No `[NOTE FOR PM]` callouts remain; acceptable given the closure, though the budget tension below deserved one.

### Findings
- **medium** Budget risk asserted, not decided (§5 NFR-1, FR-12) — NFR-1 says the default volume "must fit within the budget, otherwise the `.env` default is lowered", but no one decides *when* that check happens or what is cut first (Dataproc runs, Iceberg DCU-hours, Cloud Run, Coldline/Archive early-deletion charges at teardown per §6). *Fix:* add a pre-build cost estimate step (or a D-11 deferred item with trigger "before first full-size Dataproc run") and an ordered degrade list.

## Substance over theater — strong
Two named protagonists (Dana, Sam) both drive FRs (FR-8/9/29/30; FR-20/21). NFRs carry product-specific thresholds (USD 5, 45 min on ~7 GB runner, 15 min push-to-deploy, bytes-billed caps). The Vision is specific to this repo ("measure how well it resolves identities instead of just claiming it does"). Nothing reads as furniture.

### Findings
- **low** JTBD personas without scenarios (§2.1) — the analyst and "future client buyer" have no UJ; harmless for a portfolio PRD, but the buyer JTBD is served only by flagged-off renderers (FR-27) and §8.4. *Fix:* none needed; optionally note the buyer is served by documentation, not a flow.

## Strategic coherence — strong
The thesis is clear in §1 and the success metrics validate it rather than activity: SM-1 (MPI quality on held-out seed), SM-2 (config-only onboarding), SM-3 (cost). Counter-metrics SM-C1..C4 each name what they counterbalance, and SM-C1 (false merge ≤ 0.5%) correctly constrains SM-1/SM-7. Scope kind is a platform/capability POC and the "no MVP cut" decision is owned honestly.

### Findings
- **high** Evaluation leakage via steward decisions (FR-17, FR-20, FR-21, UJ-2, SM-7) — FR-17 says the model is "never trained on evaluation-seed data", yet SM-7 measures the steward queue "on the evaluation seed" and UJ-2/FR-20/FR-21 make every steward decision "a labeled training example". If stewards decide evaluation-seed pairs, retraining (FR-21) trains on evaluation data and SM-1/SM-C1 stop being held-out measurements — the PRD's headline claim. *Fix:* state that steward decisions on evaluation-seed pairs are excluded from training (or that stewarding runs only on the training seed / a separate review seed), and that FR-21 promotion compares metrics on an untouched evaluation slice.
- **medium** SM-10 measures a loop the PRD says is not the inner loop (§4.12 vs SM-10, NFR-10) — §4.12 makes the CLI the primary iteration loop and defers Actions end-to-end testing to "a late Phase 1 milestone", yet SM-10 needs a median over "the last 10 `main` deploys". The metric may have no data during most of the POC. *Fix:* scope SM-10 to post-milestone deploys, or add a CLI-apply timing metric for the actual inner loop.

## Done-ness clarity — adequate
Most FRs have crisp, testable consequences (FR-1 SHA-256 equality, FR-14 idempotent reload adds zero rows, FR-22 void/replacement arithmetic, FR-24 NDC normalization, FR-30 zero diff outside `config/`). A handful lean on adjectives or on the architecture.

### Findings
- **medium** FR-7 has one thin consequence (§4.2 FR-7) — "names the raw file it came from, and it can be regenerated" does not say what "line-oriented" must contain (segment per line? loop context preserved?) or how regeneration is verified (byte-equal?). *Fix:* add "regenerating from the raw file yields a byte-identical derived file" and the minimum structure Silver relies on.
- **medium** FR-40 regression undefined (§4.12 FR-40) — "an end-to-end regression against the last green run pass" has no comparison criterion. *Fix:* reuse NFR-2/SM-5 — identical Gold row counts, hash-key sets and MPI metrics within tolerance on the CI volume.
- **low** FR-25 "deployed cheaply" (§4.8) — adjective, though rescued by min-instances 0 and NFR-1. *Fix:* drop "cheaply" or tie to an idle-cost bound.
- **low** FR-38 CLI/Actions mutual exclusion unverifiable (§4.12 FR-38) — "CLI applies ... do not run while a `main` deploy is running" has no mechanism or test. *Fix:* name the mechanism at PRD level (e.g. shared Terraform state lock plus a run-lock check in the `make` target) or move to architecture.
- **low** FR-34 delegates enforcement list (§4.11) — "The architecture lists each enforcement point" is fine given the spine companion, but the CI check covers only "dbt profile or job config"; Streamlit and MPI extract clients are not checked. *Fix:* extend the CI check to all four engines listed in the FR.

## Scope honesty — strong
§7 Non-Goals, §8.3 Out of Scope and the §8.4 Future Enhancement table (each with a trigger) do real work. Seven `[ASSUMPTION]` tags on a green-light PRD is a reasonable density, and D-9 gives them an owner and trigger.

### Findings
- **medium** Payer C onboarding straddles phases (§8.1, §8.2, SM-2, FR-30) — SM-2 is measured in Phase 1 by onboarding Payer C, but the only FR whose consequence is the Payer C CI job is FR-30, which is Phase 2. Phase 1 thus has no FR owning the measuring job. *Fix:* move the FR-30 CI-job consequence into FR-29 (Phase 1) and leave only the guide in FR-30.
- **low** Assumption hardened into a counter-metric (FR-4, SM-C3) — the 2% ± 0.5 pp edge-case rate is `[ASSUMPTION]` in FR-4 but a hard constraint in SM-C3. *Fix:* reference the assumption in SM-C3 or confirm the value.

## Downstream usability — strong
Glossary is thorough and used consistently (schema fingerprint, quarantine, match band, golden person key). FR/SM IDs resolve; the spine companion is named with its AD range. Sections stand alone reasonably well.

### Findings
- **low** FR numbering not in reading order (§4.1) — FR-36 and FR-37 sit between FR-4 and FR-5; FR-38..40 follow FR-35. Unique and contiguous, but story slicing by range (e.g. §9 "FR-1 to FR-4 and FR-36 and FR-37") is error-prone. *Fix:* acceptable as-is; optionally add a feature→FR index.

## Shape fit — strong
Single-operator, brownfield, chain-top PRD: capability-spec shape with two UJs is right-sized. Brownfield references (§9 conflicts 1–10, addendum §F reuse map) are concrete and name actual files/workflows.

### Findings
- **low** Brownfield version drift (§9 item 10, addendum §D) — the addendum pins Terraform 1.16.5 while the most recent repo commit standardised on 1.15.8; §9 acknowledges the gap generically. *Fix:* name the current-vs-target pins in §9 item 10 so the first upgrade story is unambiguous.

## Mechanical notes
- Assumptions Index roundtrip: all 7 inline `[ASSUMPTION]` tags are indexed; index order is not document order (FR-10 before FR-1). The addendum's `[ASSUMPTION]` (15 min) duplicates NFR-10 — fine.
- Glossary drift: UJ-2 "scored 72%" vs glossary match score as probability (0.72); "golden key" / "member key" aliases are declared in the glossary — OK.
- NFR-1 has a lowercase sentence start ("the Streamlit dashboard runs ...").
- §8.2 bullet "FR-29 and Iceberg Bronze moved to Phase 1 (§8.1)" is redundant with §8.1.
- §9 "Net new" omits FR-5..7, FR-12, FR-28 (treated as partly reusable) — say so explicitly or list them.
- D-3 and D-8 are "Closed" yet sit in a "Deferred" table; consider moving to the resolved list.
- Required sections for stakes and type are present.
