terraform {
  required_version = ">= 1.5"

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 6.50"
    }
  }

  # Bucket is created out-of-band; Terraform cannot manage its own state store.
  backend "gcs" {
    bucket = "gitops-iceberg-data-platform-tfstate"
    prefix = "terraform/dev"
  }
}

provider "google" {
  project = var.project_id
  region  = var.region
}

# Required by the Dataproc Serverless batches in the release workflow.
resource "google_project_service" "dataproc" {
  project = var.project_id
  service = "dataproc.googleapis.com"

  # Leave the API enabled on destroy; other workloads in the project may rely on it.
  disable_on_destroy = false
}

# Required by the BigLake connection created in the bq_iceberg module.
resource "google_project_service" "bigqueryconnection" {
  project = var.project_id
  service = "bigqueryconnection.googleapis.com"

  disable_on_destroy = false
}

module "data_platform" {
  source = "../../modules/bq_iceberg"

  project_id               = var.project_id
  region                   = var.region
  force_destroy            = var.force_destroy
  pipeline_service_account = var.pipeline_service_account

  depends_on = [google_project_service.bigqueryconnection]
}

# -----------------------------------------------------------------
# Outputs – surfaced from the module for convenience
# -----------------------------------------------------------------
output "iceberg_warehouse_bucket" {
  value = module.data_platform.iceberg_warehouse_bucket
}

output "bq_connection_id" {
  value = module.data_platform.bq_connection_id
}

output "bq_connection_service_account" {
  value = module.data_platform.bq_connection_service_account
}
