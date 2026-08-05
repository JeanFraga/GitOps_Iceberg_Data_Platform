terraform {
  required_version = ">= 1.5"

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 5.0"
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

module "data_platform" {
  source = "../../modules/bq_iceberg"

  project_id               = var.project_id
  region                   = var.region
  bq_dataset_id            = "gold_star_schema"
  force_destroy            = var.force_destroy
  pipeline_service_account = var.pipeline_service_account
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
