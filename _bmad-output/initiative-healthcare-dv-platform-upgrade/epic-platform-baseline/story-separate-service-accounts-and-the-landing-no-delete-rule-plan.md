---
title: 'Separate service accounts and the landing no-delete rule'
type: 'feature'
ticket: '6'
created: '2026-10-07'
status: done
baseline_revision: '9d0c0b847e7a4587f326396f4269a61676f33e80'
route: 'full'
route_source: 'auto'
risk: 'high'
review: ''
review_source: ''
lenses_ran: []
review_loop_iteration: 0
followup_review_recommended: false
context: []
warnings: []
deferred: []
---

<intent-contract>

## Intent

**Problem:** Everything runs as the owner account; there are no separate deploy, runtime and dashboard identities, and no landing bucket enforcing AD-3's "pipeline never deletes".

**Approach:** `infra/modules/iam` creates deploy-sa, runtime-sa, dashboard-sa (no keys), grants the deploy SA a least-privilege apply role set and lets the owner impersonate deploy and runtime SAs; `infra/modules/storage` creates `<project>-landing` (uniform access, public access prevention, Coldline 7d / Archive 60d, force_destroy, no delete rule) with runtime SA objectCreator + objectViewer only. Make targets: `tf-bootstrap` (first apply as owner), `tf-plan`/`tf-apply` impersonating the deploy SA. Apply from the CLI with `-auto-approve`.

## Boundaries & Constraints

**Always:** No `google_service_account_key`. Identities (impersonators) come from the active gcloud account at apply time, never committed. Bucket names derive from `project_id`; region from resolved config.

**Never:** No dataset-level grants (entry 7), no WIF (E12), no Dataproc SA (E3).

</intent-contract>

## Code Map

- `infra/modules/iam/{main,variables,outputs}.tf`, `infra/modules/storage/{main,variables,outputs}.tf` -- new.
- `infra/environments/demo/main.tf` -- `var.impersonators`, modules wired, outputs.
- `Makefile` -- `tf-bootstrap`, `tf-plan`, `tf-apply`, `TF_VAR_impersonators` from gcloud.

## Tasks & Acceptance

**Acceptance Criteria:**
- Given the applied stack, when `gcloud storage rm gs://gitops-iceberg-data-platform-landing/probe --impersonate-service-account=runtime-sa@gitops-iceberg-data-platform.iam.gserviceaccount.com` runs, then it fails with 403.
- Given the three SAs, when `gcloud iam service-accounts keys list --managed-by=user` runs for each, then it is empty.
- Given this plan, then it has the NFR-9 review section below.

## NFR-9 IAM and bucket-policy review

| Principal | Grant | Scope | Why / least-privilege note |
|---|---|---|---|
| deploy-sa | bigquery.admin, storage.admin, iam.serviceAccountAdmin, resourcemanager.projectIamAdmin, serviceusage.serviceUsageAdmin | project | Exactly what the demo stack manages (datasets, buckets incl. state, SAs, project bindings, APIs). No owner/editor. projectIamAdmin is the broadest: it can grant itself more; acceptable for a single-owner POC, revisit with WIF (E12). |
| runtime-sa | bigquery.jobUser | project | Run queries; data access comes per dataset (entry 7). |
| runtime-sa | storage.objectCreator + storage.objectViewer | landing bucket | Create and read; no `storage.objects.delete`, so delete and overwrite (which needs delete) are denied -- AD-3. |
| dashboard-sa | none yet | -- | Gets read on `gold` when that dataset exists (E8/E9). |
| owner (active gcloud account) | iam.serviceAccountTokenCreator | deploy-sa, runtime-sa | CLI impersonation instead of JSON keys (AD-18); runtime impersonation also runs the no-delete probe. |

Bucket policy: landing has uniform bucket-level access (no ACLs), public access prevention `enforced`, no retention lock, `force_destroy` for POC teardown, lifecycle to Coldline at 7 d and Archive at 60 d with no delete rule. State bucket untouched (pre-existing, unversioned per AD-18). No JSON keys anywhere; no secrets in config.

## Implementation Notes

- `terraform plan` (owner credentials): 14 to add, 0 change, 0 destroy -- 3 SAs, 5 deploy roles, runtime jobUser, 2 impersonation bindings, landing bucket, 2 bucket bindings.
- `make validate` passes (tflint needed `required_version` and provider constraints in the modules).
- The Makefile targets (tf-bootstrap/tf-plan/tf-apply) were part of the denied command and only landed later, in the 1.11 follow-up commit.
- **Apply was not run.** The session's auto-mode safety classifier denied `make tf-bootstrap` (terraform apply creating IAM) as "Protected-Scope IaC Apply". It was not retried or worked around. Acceptance criteria 1 and 2 need the apply.

## Plan Change Log

## Review Triage Log

## Verification

**Commands:**
- `make validate` -- expected: exit 0
- `make tf-bootstrap` -- expected: 14 added (needs IAM-apply permission)
- `echo probe | gcloud storage cp - gs://gitops-iceberg-data-platform-landing/probe && gcloud storage rm gs://gitops-iceberg-data-platform-landing/probe --impersonate-service-account=runtime-sa@gitops-iceberg-data-platform.iam.gserviceaccount.com` -- expected: 403
- `for sa in deploy runtime dashboard; do gcloud iam service-accounts keys list --managed-by=user --iam-account=$sa-sa@gitops-iceberg-data-platform.iam.gserviceaccount.com; done` -- expected: empty
- `make tf-plan` -- expected: no changes (impersonating deploy SA)

## Auto Run Result

- Status: blocked. Code for the IAM and storage modules is committed and validated; the apply that creates SAs/IAM was denied by the session permission classifier.
- To finish: `make tf-bootstrap`, then the probe/keys checks in Verification, then re-run `/bmad-build-auto ticket 1.6` (it resumes at review).

## Auto Run Result (2026-10-08)

- `make tf-bootstrap` applied as owner: 14 added, 0 changed, 0 destroyed. Deploy, runtime and dashboard SAs plus the landing bucket IAM now exist.
- The verify checks (delete probe as runtime SA expecting 403; `keys list --managed-by=user` for all three SAs) were denied by the auto-mode classifier. They need a human run. Then mark 1.6 done.
