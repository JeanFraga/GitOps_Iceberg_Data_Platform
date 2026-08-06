terraform {
  required_version = ">= 1.5"

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 5.0"
    }
  }
}

# -----------------------------------------------------------------
# GCS Bucket – Iceberg warehouse storage
# -----------------------------------------------------------------
resource "google_storage_bucket" "iceberg_warehouse" {
  name                        = "${var.project_id}-iceberg-warehouse"
  location                    = var.region
  uniform_bucket_level_access = true
  force_destroy               = var.force_destroy

  versioning {
    enabled = false
  }

  lifecycle_rule {
    condition {
      age = 90
    }
    action {
      type          = "SetStorageClass"
      storage_class = "NEARLINE"
    }
  }
}

# -----------------------------------------------------------------
# BigQuery Dataset – Gold star-schema layer
# -----------------------------------------------------------------
resource "google_bigquery_dataset" "iceberg_dataset" {
  dataset_id                 = var.bq_dataset_id
  location                   = var.region
  delete_contents_on_destroy = var.force_destroy
}

# -----------------------------------------------------------------
# BigQuery Dataset – Silver layer (holds the BigLake external table
# registered by the release workflow)
# -----------------------------------------------------------------
resource "google_bigquery_dataset" "silver_dataset" {
  dataset_id                 = var.silver_dataset_id
  location                   = var.region
  delete_contents_on_destroy = var.force_destroy
}

# -----------------------------------------------------------------
# BigQuery Connection – BigLake / GCS federation
# -----------------------------------------------------------------
resource "google_bigquery_connection" "gcs_connection" {
  connection_id = var.bq_connection_id
  location      = var.region
  cloud_resource {}
}

# -----------------------------------------------------------------
# IAM – BigLake service account needs objectAdmin on the bucket
# -----------------------------------------------------------------
resource "google_storage_bucket_iam_member" "bq_connection_gcs_admin" {
  bucket = google_storage_bucket.iceberg_warehouse.name
  role   = "roles/storage.objectAdmin"
  member = "serviceAccount:${google_bigquery_connection.gcs_connection.cloud_resource[0].service_account_id}"
}

# Allow the Dataproc Serverless / pipeline SA to read+write the bucket
resource "google_storage_bucket_iam_member" "pipeline_sa_gcs_admin" {
  count  = var.pipeline_service_account != "" ? 1 : 0
  bucket = google_storage_bucket.iceberg_warehouse.name
  role   = "roles/storage.objectAdmin"
  member = "serviceAccount:${var.pipeline_service_account}"
}

# Allow the pipeline SA to run BigQuery jobs
resource "google_project_iam_member" "pipeline_sa_bq_job_user" {
  count   = var.pipeline_service_account != "" ? 1 : 0
  project = var.project_id
  role    = "roles/bigquery.jobUser"
  member  = "serviceAccount:${var.pipeline_service_account}"
}

# Creating BigLake external tables through the connection requires
# bigquery.connections.delegate, which only connectionAdmin carries
# (connectionUser has get/list/use but NOT delegate). Granted at project
# level: the CI service account can set project IAM (it manages the jobUser
# binding above) but lacks bigquery.connections.setIamPolicy, so a
# connection-scoped google_bigquery_connection_iam_member cannot be applied.
# The release workflow authenticates as this same SA (GCP_SA_KEY), so the
# registration step depends on this grant.
resource "google_project_iam_member" "pipeline_sa_connection_admin" {
  count   = var.pipeline_service_account != "" ? 1 : 0
  project = var.project_id
  role    = "roles/bigquery.connectionAdmin"
  member  = "serviceAccount:${var.pipeline_service_account}"
}
