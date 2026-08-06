terraform {
  required_version = ">= 1.5"

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 5.0"
    }
    # Only for google_project_service_identity (service-agent provisioning).
    google-beta = {
      source  = "hashicorp/google-beta"
      version = "~> 5.0"
    }
  }
}

data "google_project" "this" {
  project_id = var.project_id
}

# -----------------------------------------------------------------
# Service account the Composer environment (and its DAG tasks) run as
# -----------------------------------------------------------------
resource "google_service_account" "composer" {
  account_id   = "${var.environment_name}-sa"
  display_name = "Cloud Composer environment for the NYC taxi pipeline"
}

# Composer control-plane requirement for the environment SA.
resource "google_project_iam_member" "composer_worker" {
  project = var.project_id
  role    = "roles/composer.worker"
  member  = "serviceAccount:${google_service_account.composer.email}"
}

# Provision the Composer service agent deterministically: granting IAM to
# service-<num>@cloudcomposer-accounts before the agent exists fails with an
# eventually-consistent 400 on first apply after API enablement.
resource "google_project_service_identity" "composer_agent" {
  provider = google-beta
  project  = var.project_id
  service  = "composer.googleapis.com"
}

# The Composer service agent needs this on the environment SA (scoped grant,
# matching Google's Composer Terraform example).
resource "google_service_account_iam_member" "composer_service_agent" {
  service_account_id = google_service_account.composer.name
  role               = "roles/composer.ServiceAgentV2Ext"
  member             = "serviceAccount:${google_project_service_identity.composer_agent.email}"
}

# ----- Data-plane roles used by the DAG tasks ---------------------
# Mirrors what the CI pipeline SA needs (see infra/modules/bq_iceberg):
# submit Dataproc batches, read/write the warehouse bucket, run BQ jobs,
# re-register the Silver BigLake table, and let dbt build gold tables.
resource "google_project_iam_member" "composer_dataproc_editor" {
  project = var.project_id
  role    = "roles/dataproc.editor"
  member  = "serviceAccount:${google_service_account.composer.email}"
}

resource "google_storage_bucket_iam_member" "composer_warehouse_admin" {
  bucket = var.iceberg_warehouse_bucket
  role   = "roles/storage.objectAdmin"
  member = "serviceAccount:${google_service_account.composer.email}"
}

resource "google_project_iam_member" "composer_bq_job_user" {
  project = var.project_id
  role    = "roles/bigquery.jobUser"
  member  = "serviceAccount:${google_service_account.composer.email}"
}

# connectionAdmin (not connectionUser) is required for the delegate
# permission used by CREATE EXTERNAL TABLE ... WITH CONNECTION; see the
# matching grant and comment in infra/modules/bq_iceberg.
resource "google_project_iam_member" "composer_bq_connection_admin" {
  project = var.project_id
  role    = "roles/bigquery.connectionAdmin"
  member  = "serviceAccount:${google_service_account.composer.email}"
}

# Project-level for PoC simplicity (covers gold writes + silver reads);
# tighten to dataset-level grants when promoting to production.
resource "google_project_iam_member" "composer_bq_data_editor" {
  project = var.project_id
  role    = "roles/bigquery.dataEditor"
  member  = "serviceAccount:${google_service_account.composer.email}"
}

# Dataproc Serverless batches run as the Compute Engine default SA (same as
# the CI-submitted batches); submitting on its behalf requires actAs.
resource "google_service_account_iam_member" "composer_act_as_compute_default" {
  service_account_id = "projects/${var.project_id}/serviceAccounts/${data.google_project.this.number}-compute@developer.gserviceaccount.com"
  role               = "roles/iam.serviceAccountUser"
  member             = "serviceAccount:${google_service_account.composer.email}"
}

# -----------------------------------------------------------------
# Composer 3 environment – smallest preset to keep PoC cost down.
# NOTE: a Composer environment bills continuously (~$10-12/day even at
# this size) and cannot be paused; flip composer_enabled=false in
# infra/environments/dev to destroy it between testing sessions.
# -----------------------------------------------------------------
resource "google_composer_environment" "this" {
  name   = var.environment_name
  region = var.region

  labels = {
    environment = "dev"
    purpose     = "incremental-loads-poc"
  }

  config {
    environment_size = "ENVIRONMENT_SIZE_SMALL"

    node_config {
      service_account = google_service_account.composer.email
    }

    software_config {
      image_version = var.image_version

      # Single source of runtime config for the DAG (read via os.environ).
      env_variables = {
        GCP_PROJECT_ID = var.project_id
        GCP_REGION     = var.region
      }

      # dbt runs in-image (a per-run venv would not fit the SMALL preset's
      # worker storage). Keep the range in sync with
      # src/dbt_project/requirements.txt; changing it triggers a ~20 min
      # environment update.
      pypi_packages = {
        dbt-bigquery = ">=1.12,<2.0"
      }
    }
  }

  depends_on = [
    google_project_iam_member.composer_worker,
    google_service_account_iam_member.composer_service_agent,
  ]
}
