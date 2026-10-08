# Landing bucket (AD-3): immutable, content-hashed objects; the pipeline never deletes.
# Runtime SA gets create + read only there, so delete and overwrite are denied by IAM.
# Warehouse bucket (AD-4) holds Iceberg data; the runtime SA writes it freely.

terraform {
  required_version = ">= 1.16.5"

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = ">= 8.6.0"
    }
  }
}

resource "google_storage_bucket" "landing" {
  project                     = var.project_id
  name                        = "${var.project_id}-landing"
  location                    = var.region
  uniform_bucket_level_access = true
  public_access_prevention    = "enforced"
  # POC teardown: no retention lock, so terraform destroy removes the bucket (AD-3).
  force_destroy = true

  lifecycle_rule {
    condition {
      age = 7
    }
    action {
      type          = "SetStorageClass"
      storage_class = "COLDLINE"
    }
  }

  lifecycle_rule {
    condition {
      age = 60
    }
    action {
      type          = "SetStorageClass"
      storage_class = "ARCHIVE"
    }
  }
}

resource "google_storage_bucket_iam_member" "runtime_create" {
  bucket = google_storage_bucket.landing.name
  role   = "roles/storage.objectCreator"
  member = var.runtime_member
}

resource "google_storage_bucket_iam_member" "runtime_read" {
  bucket = google_storage_bucket.landing.name
  role   = "roles/storage.objectViewer"
  member = var.runtime_member
}

# Warehouse bucket (Iceberg data + metadata) and its BigLake REST catalog.
resource "google_storage_bucket" "warehouse" {
  project                     = var.project_id
  name                        = "${var.project_id}-warehouse"
  location                    = var.region
  uniform_bucket_level_access = true
  public_access_prevention    = "enforced"
  # POC teardown (AD-4).
  force_destroy = true
}

# Runtime SA writes Bronze Iceberg tables.
resource "google_storage_bucket_iam_member" "runtime_warehouse" {
  bucket = google_storage_bucket.warehouse.name
  role   = "roles/storage.objectAdmin"
  member = var.runtime_member
}

resource "google_project_service" "biglake" {
  project            = var.project_id
  service            = "biglake.googleapis.com"
  disable_on_destroy = false
}

resource "google_biglake_iceberg_catalog" "warehouse" {
  project      = var.project_id
  name         = google_storage_bucket.warehouse.name
  catalog_type = "CATALOG_TYPE_GCS_BUCKET"

  depends_on = [google_project_service.biglake]
}
