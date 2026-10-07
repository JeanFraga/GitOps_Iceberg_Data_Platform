# Landing bucket (AD-3): immutable, content-hashed objects; the pipeline never deletes.
# Runtime SA gets create + read only, so delete and overwrite are denied by IAM.

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
