terraform {
  required_version = ">= 1.5"

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 5.0"
    }
    google-beta = {
      source  = "hashicorp/google-beta"
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

# Used by the composer module's google_project_service_identity only.
provider "google-beta" {
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

# Required by the Cloud Composer environment (composer module).
resource "google_project_service" "composer" {
  count   = var.composer_enabled ? 1 : 0
  project = var.project_id
  service = "composer.googleapis.com"

  disable_on_destroy = false
}

# Required by the Looker (Google Cloud core) instance (looker module).
resource "google_project_service" "looker" {
  count   = var.looker_enabled ? 1 : 0
  project = var.project_id
  service = "looker.googleapis.com"

  disable_on_destroy = false
}

# Listed by Google as a Looker instance prerequisite. Strictly it is only
# needed for private-connections (private services access) instances; this
# module provisions a public-IP instance, so it is enabled defensively to
# match the documented prerequisite list rather than out of proven necessity.
resource "google_project_service" "servicenetworking" {
  count   = var.looker_enabled ? 1 : 0
  project = var.project_id
  service = "servicenetworking.googleapis.com"

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

# Daily incremental-load orchestration. Gated behind composer_enabled: the
# environment bills continuously (~$10-12/day even at the smallest size), so
# flip the flag to false and apply to tear it down between testing sessions.
module "composer" {
  count  = var.composer_enabled ? 1 : 0
  source = "../../modules/composer"

  project_id               = var.project_id
  region                   = var.region
  iceberg_warehouse_bucket = module.data_platform.iceberg_warehouse_bucket

  depends_on = [google_project_service.composer]
}

# BI demo layer. Gated behind looker_enabled and defaulted off: the
# instance takes ~60 minutes to create, needs Looker quota on the project,
# and needs an OAuth client that cannot be created by Terraform. See
# infra/modules/looker/README-prereqs.md before flipping this on.
module "looker" {
  count  = var.looker_enabled ? 1 : 0
  source = "../../modules/looker"

  project_id          = var.project_id
  region              = var.region
  gold_dataset_id     = module.data_platform.bq_dataset_id
  oauth_client_id     = var.looker_oauth_client_id
  oauth_client_secret = var.looker_oauth_client_secret

  # module.data_platform is listed explicitly: the only implicit link is the
  # gold_dataset_id output, which depends on the dataset alone, not on the
  # roles/looker.admin grant the instance create needs. Without this the two
  # run in parallel and the create can beat IAM propagation — the same
  # eventual-consistency failure the composer module guards against.
  depends_on = [
    google_project_service.looker,
    google_project_service.servicenetworking,
    module.data_platform,
  ]
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

output "composer_dag_gcs_prefix" {
  value = one(module.composer[*].dag_gcs_prefix)
}

output "composer_airflow_uri" {
  value = one(module.composer[*].airflow_uri)
}

output "looker_uri" {
  value = one(module.looker[*].looker_uri)
}

output "looker_bq_service_account" {
  value = one(module.looker[*].bq_service_account)
}
