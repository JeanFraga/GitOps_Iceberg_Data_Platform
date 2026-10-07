---
title: Healthcare Domain Review - PRD healthcare-dv-platform-upgrade
reviewer: healthcare data domain expert (subagent)
date: 2026-10-07
verdict: PASS WITH REQUIRED CHANGES
---

# Healthcare Domain Review

**Verdict: Pass, with required changes.** The overall shape is sound: payer and EMR feeds, schema eras, a vault, an MPI measured against ground truth, and PHI patterns. Several domain-modelling errors would show up right away to a healthcare reviewer or client. Fix them in the PRD before architecture work, because they change the hub and link design.

## Findings

### F1 (critical): Member identity is payer-scoped, and the patient is a separate entity
- FR-13 says "the same business key from two sources produces the same hub hash key". Payer member IDs are only unique inside one payer, so `M12345` at Payer A and `M12345` at Payer B are different people. Hashing them together creates false merges before the MPI even runs, and it hides the MPI's job.
- Subscriber and dependents: in 834 and 837, the subscriber ID is shared across the family, and a dependent is identified by a person/suffix code (2000/2100 loops, INS segment). The business key must be `payer_id + member_id + person_code`, or something equivalent.
- The EMR (FHIR Patient and MRN) is a **patient**, not a member. The PRD has no FHIR `Patient` resource and no patient hub, yet `DIM_PATIENTS` and the MPI are supposed to merge payer and EMR identities. The fix: put a composite key with the record-source/assigning-authority qualifier into `HUB_MEMBER` (or a `HUB_PERSON`), add FHIR `Patient` to FR-2, and make the MPI resolve members and EMR patients together.

### F2 (critical): Claim grain, and adjudicated versus submitted claims
- There is `HUB_CLAIM` plus `SAT_CLAIM_LINES`, but no line grain. An 837 has a header (CLM, header-level diagnosis codes in HI) and service lines (LX/SV1/SV2/SV3). Add a claim-line key: either `HUB_CLAIM_LINE` with `LINK_CLAIM_LINE`, or a multi-active satellite keyed on the line number. Split `SAT_CLAIM_HEADER` from `SAT_CLAIM_LINE`.
- Claim versions: 837 frequency codes (CLM05-3: 1 original, 7 replacement, 8 void) and payer adjustments create several versions of one claim. Without a rule for the latest effective version, `FCT_CLAIMS_MONTHLY` double-counts. Add this to FR-14 and FR-22 and to the generator.
- An 837 is a **submitted** claim. It carries billed amounts, not paid amounts. Paid amounts, allowed amounts, patient responsibility (CAS PR group) and adjudication status come from the **835** remittance or from a payer's adjudicated claims extract. FR-22 cannot be computed from the 837 alone. Add a synthetic 835 (or an adjudicated flat extract) to FR-1 and FR-2.
- A pharmacy (NCPDP) claim has no hub, link or satellite. Add it, keyed on Rx number + fill number + pharmacy NCPDP/NPI + date of service.

### F3 (high): Eligibility is not modelled, and HEDIS needs it
- The 834 is generated, but the vault has no eligibility or coverage structure. HEDIS denominators depend on **continuous enrollment** with allowable gaps, the product line (Commercial, Medicaid, Medicare) and the anchor date. Add an eligibility satellite or `HUB_COVERAGE` with effective and term dates, product/plan, and relationship to the subscriber. Add the 834 maintenance codes (INS03 021 add, 024 term, 001 change) and full versus change files to the generator.
- Add a HEDIS-shaped stub that is concrete and public. One option is a denominator for Breast Cancer Screening (BCS-E) or Comprehensive Diabetes Care–style measures, from age, sex and continuous enrollment, with value sets marked illustrative. NCQA value sets are licensed, so use public CMS eCQM/VSAC-style codes or invented OIDs.
- For CMS-style exports, name one public layout, for example an MA encounter-data-like or T-MSIS-like flat extract, and label it illustrative.

### F4 (high): Code systems and licensing
- `DIM_DIAGNOSES (ICD-10/CPT)` mixes diagnoses with procedures. Split it into `DIM_DIAGNOSIS` (ICD-10-CM) and `DIM_PROCEDURE` (CPT/HCPCS, and ICD-10-PCS for 837I inpatient), plus revenue codes (837I), place of service, DRG (inpatient) and CDT (837D dental).
- **CPT is copyrighted by the AMA.** A public portfolio repo must not ship CPT descriptors or real code lists. Use public HCPCS Level II, public ICD-10-CM/PCS files from CMS, and generated CPT-shaped codes without descriptors. CDT (ADA) has the same issue.
- NDC: generate 10-digit NDCs in their 4-4-2, 5-3-2 and 5-4-1 forms, and test normalization to 11-digit 5-4-2. This is a classic real-world drift case and a good one for the portfolio.
- NPI: generate NPIs with a valid Luhn check digit (prefix 80840). Add a provider hub (NPI). The ML fallback already uses "provider patterns", but no provider entity exists.

### F5 (medium): PHI governance patterns
- NFR-4's "de-identified view" should name the HIPAA **Safe Harbor** rules: remove the 18 identifiers, generalize ZIP to 3 digits (000 for low-population ZIP3s), keep only the year of dates, cap ages at 90+. Also note that a hashed SSN or member ID is **not** de-identified. Use a keyed HMAC or token, and keep the key outside the warehouse.
- Use BigQuery policy tags (column-level security) and dynamic data masking on PHI columns. These are free and show the pattern well.
- The steward UI is PHI-by-design (side-by-side demographics). Even with synthetic data, label any public deployment and default to local only, to be consistent with NFR-4.
- Do not put SSN in a hashdiff that is exposed outside restricted datasets. Store it in a separate restricted satellite (`SAT_MEMBER_SENSITIVE`), which is the standard DV pattern for splitting PHI.

### F6 (medium): Synthetic realism for MPI testing
- Add these noise types: last-name changes (marriage), hyphenated and compound Hispanic surnames, name-order swaps in Asian names, newborns with placeholder names ("BABY GIRL SMITH") and the mother's member ID, Jr/Sr generations at one address, and shared or default SSNs (999-xx, 123-45-6789).
- Households: dependents in a family share the subscriber ID, address and phone. This is the hardest negative case, and the most realistic one.
- Plan switching between payers over time (2022 to the present) is the main real-world reason for cross-payer matches. Model it explicitly, with coverage gaps.
- FHIR-to-claim linkage (`LINK_VISIT_CLAIM`) has no shared key in the real world. It is matched on patient + date of service + NPI + facility. The generator should not emit a perfect claim_id on Encounter. Otherwise, emit it as ground truth only.
- A ~2% edge-case rate and F1 ≥ 0.97 are plausible. Report the false-merge rate (overlinking) separately. In healthcare, a false merge is a patient-safety issue and costs far more than a missed match. Weight thresholds with that in mind.

### F7 (low): Smaller points
- An FHIR R4 Encounter should reference Patient, Practitioner and Organization. Use US Core profiles as the shape reference.
- The 837 variants: 837P (CMS-1500 equivalent) and 837I (UB-04 equivalent, with type of bill, admission/discharge dates and revenue codes) need distinct canonical columns. A single canonical claims schema needs claim-type-specific nullable sections.
- X12 version: state 005010X222A1 (837P), 005010X223A2 (837I), 005010X224A2 (837D), 005010X220A1 (834) and 005010X221A1 (835) as shape references, "not certified".
- Synthea (Apache-2.0) is a good optional source of clinical realism. You can generate its output once and commit a small sample, which avoids needing Java in CI.

## Required PRD Changes (summary)
1. Make member business keys payer-qualified, add a person code, and add FHIR Patient plus a patient/person entity in the MPI (FR-2, FR-13, §3).
2. Add claim header/line grain, claim version/void handling, an 835 or adjudicated extract, and the pharmacy claim vault objects (FR-2, FR-14, FR-22).
3. Add eligibility/coverage vault objects and continuous-enrollment logic for HEDIS stubs (FR-14, FR-25).
4. Split the diagnosis and procedure dimensions, address CPT/CDT licensing, and add the NDC normalization, NPI Luhn check and provider hub requirements (FR-2, FR-23).
5. Specify Safe Harbor de-identification, HMAC tokenization, BigQuery policy tags and a restricted PHI satellite (NFR-4).
6. Extend the noise taxonomy (households, newborns, name changes, plan switching), and add a false-merge-rate metric to SM-1.
