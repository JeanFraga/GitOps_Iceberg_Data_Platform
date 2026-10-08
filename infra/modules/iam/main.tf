# Deploy, runtime and dashboard service accounts (AD-14, AD-18, NFR-9).
# No google_service_account_key anywhere: CLI impersonates, Actions uses WIF (E12).

terraform {
  required_version = ">= 1.16.5"

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = ">= 8.6.0"
    }
  }
}

locals {
  # Least privilege for Terraform applies on this project: datasets, buckets, SAs,
  # project IAM bindings and API enablement. No roles/owner or roles/editor.
  deploy_roles = [
    "roles/bigquery.admin",
    "roles/storage.admin",
    "roles/iam.serviceAccountAdmin",
    "roles/resourcemanager.projectIamAdmin",
    "roles/serviceusage.serviceUsageAdmin",
  ]
}

resource "google_service_account" "deploy" {
  project      = var.project_id
  account_id   = "deploy-sa"
  display_name = "Deploy (Terraform) service account"
}

resource "google_service_account" "runtime" {
  project      = var.project_id
  account_id   = "runtime-sa"
  display_name = "Pipeline runtime service account"
}

resource "google_service_account" "dashboard" {
  project      = var.project_id
  account_id   = "dashboard-sa"
  display_name = "Dashboard (read-only Gold) service account"
}

resource "google_project_iam_member" "deploy" {
  for_each = toset(local.deploy_roles)
  project  = var.project_id
  role     = each.value
  member   = google_service_account.deploy.member
}

# The runtime SA runs BigQuery jobs; dataset-level grants come with the datasets (entry 7).
resource "google_project_iam_member" "runtime_job_user" {
  project = var.project_id
  role    = "roles/bigquery.jobUser"
  member  = google_service_account.runtime.member
}

# CLI impersonation: the platform owner mints tokens for the deploy SA (applies) and the
# runtime SA (local runner and the landing no-delete probe). Never JSON keys.
resource "google_service_account_iam_member" "deploy_impersonation" {
  for_each           = toset(var.impersonators)
  service_account_id = google_service_account.deploy.name
  role               = "roles/iam.serviceAccountTokenCreator"
  member             = each.value
}

resource "google_service_account_iam_member" "runtime_impersonation" {
  for_each           = toset(var.impersonators)
  service_account_id = google_service_account.runtime.name
  role               = "roles/iam.serviceAccountTokenCreator"
  member             = each.value
}

# Bronze loader (epic-landing-bronze entry 1): BigLake Iceberg REST catalog access, billed to
# this project via the x-goog-user-project header (needs serviceUsageConsumer).
resource "google_project_iam_member" "runtime_biglake" {
  for_each = toset(["roles/biglake.editor", "roles/serviceusage.serviceUsageConsumer"])
  project  = var.project_id
  role     = each.value
  member   = google_service_account.runtime.member
}
