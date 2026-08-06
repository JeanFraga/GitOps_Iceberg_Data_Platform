# Looker module — manual prerequisites

Unlike the rest of this repo, the Looker instance **cannot be applied from a
clean slate by CI alone**. Three gates sit outside Terraform. Read this before
setting `looker_enabled = true`.

## 1. Trial quota — register first

A project has **no trial quota by default**. Applying without it fails in
seconds with:

```
Error 429: AllocateQuota failed for project number <n>
when allocating quota for looker.googleapis.com/trial_instances
```

(Confirmed against this project on 2026-08-06.) The metric shows an empty
quota bucket — no `defaultLimit`, no `effectiveLimit` — which is what a
zero allocation looks like. Note the umbrella
`looker.googleapis.com/instances` quota being non-zero (3 here) does **not**
imply trial entitlement; the edition-specific metric is what gates creation.

**Fix: register for the trial**, which allocates the quota to the project:

- Registration form: <https://cloud.google.com/resources/looker-free-trial>
- Or Cloud console → Looker product page → **30-DAY TRIAL**

Only after the project shows trial quota will `terraform apply` succeed.
Requesting an increase on the quota page is not the documented path —
registration is.

Limits once granted: **one trial instance per project**, and the trial caps
entitlements at 5 Viewer, 1 Standard and 1 Developer user.

## 1a. The trial auto-converts to a PAID instance

The trial runs **30 days** (not 90 — the Terraform registry's "90 days"
wording does not match the Looker Core docs). It **cannot be extended**, and
at the end it does not expire — it *automatically converts to a paid Standard
Looker (Google Cloud core) instance*.

Treat that date as a hard deadline: destroy the instance before day 30, or
accept Standard-edition billing. Because provider 5.x has no
`deletion_policy`, plan the teardown in advance rather than discovering it on
day 31.

## 2. OAuth client — inherently a two-pass setup

`oauth_config` is a required block, and both `client_id` and `client_secret`
are required fields. The google provider has **no resource for creating an
OAuth client**, so it must be made by hand:

1. APIs & Services → OAuth consent screen → configure (Internal is fine).
2. APIs & Services → Credentials → Create credentials → OAuth client ID →
   application type **Web application**.
3. Apply with a placeholder redirect URI to create the instance.
4. Read the `looker_uri` output and add `<looker_uri>/oauth2callback` as an
   authorized redirect URI on the same client.

Step 4 is why this cannot be one pass: the redirect URI depends on the
instance URL, which does not exist until the instance is created.

Pass the values as `TF_VAR_looker_oauth_client_id` /
`TF_VAR_looker_oauth_client_secret` (mirroring how `TF_VAR_project_id` is
supplied in `.github/workflows/terraform.yml`). Do not commit them.

## 3. API + IAM

- Enable `looker.googleapis.com` — handled by `google_project_service.looker`
  in `infra/environments/dev/main.tf`.
- The caller needs `roles/looker.admin`. The CI runner currently holds
  `roles/editor` + `roles/resourcemanager.projectIamAdmin`, which does **not**
  include the Looker admin permissions, so this grant must be added before CI
  can manage the instance.

## Cost and lifecycle

- Trial edition is valid for **90 days**. Editions cannot be changed after
  creation — moving to Standard means destroy + recreate.
- Creation takes about **60 minutes** and cannot be paused or cancelled.
- Provider 5.x has no `deletion_policy` argument, so `terraform destroy` fails
  if the instance still holds nested resources
  (hashicorp/terraform-provider-google#19467). Delete dashboards and Looks in
  the UI first.

## What Terraform does not cover

Configured in the Looker UI, not in code:

- The BigQuery **connection** (name it `nyc_taxi_bigquery` to match
  `constant: connection_name` in `src/looker_project/manifest.lkml`), using the
  `bq_service_account` module output.
- The **Git connection** binding the Looker project to a repo.
- User provisioning and group/role assignment.
