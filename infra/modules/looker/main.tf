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
# Service account Looker uses to query the Gold layer.
#
# Created here so the BigQuery grants are managed in code; the actual
# binding of this SA to a Looker connection happens in the Looker UI
# (Admin > Database > Connections), which has no Terraform resource.
# -----------------------------------------------------------------
resource "google_service_account" "looker_bq" {
  account_id   = "${var.instance_name}-bq-sa"
  display_name = "Looker BigQuery connection for the NYC taxi Gold layer"
}

# Running any query requires jobUser at project level.
resource "google_project_iam_member" "looker_bq_job_user" {
  project = var.project_id
  role    = "roles/bigquery.jobUser"
  member  = "serviceAccount:${google_service_account.looker_bq.email}"
}

# Read access to the Gold tables. Scoped to the dataset rather than the
# project: unlike service-account-scoped IAM (which the CI runner cannot
# write — see infra/modules/composer), dataset IAM is covered by the
# runner's roles/editor, so least privilege is achievable here.
resource "google_bigquery_dataset_iam_member" "looker_gold_viewer" {
  project    = var.project_id
  dataset_id = var.gold_dataset_id
  role       = "roles/bigquery.dataViewer"
  member     = "serviceAccount:${google_service_account.looker_bq.email}"
}

# -----------------------------------------------------------------
# Looker (Google Cloud core) instance.
#
# NOTE ON TEARDOWN: provider 5.x has no `deletion_policy` argument on
# this resource, so `terraform destroy` cannot force-delete an instance
# that still holds nested resources and will fail with a FAILED_PRECONDITION
# (hashicorp/terraform-provider-google#19467). Delete dashboards/looks in
# the UI first, or upgrade the provider past 5.x where the argument exists.
#
# Creation takes roughly 60 minutes and cannot be paused or cancelled
# once started.
# -----------------------------------------------------------------
resource "google_looker_instance" "this" {
  name             = var.instance_name
  region           = var.region
  platform_edition = var.platform_edition

  public_ip_enabled = var.public_ip_enabled

  oauth_config {
    client_id     = var.oauth_client_id
    client_secret = var.oauth_client_secret
  }

  # Omitted entirely when no domains are supplied: an empty
  # allowed_email_domains list is not the same as "no restriction".
  dynamic "admin_settings" {
    for_each = length(var.allowed_email_domains) > 0 ? [1] : []
    content {
      allowed_email_domains = var.allowed_email_domains
    }
  }

  timeouts {
    create = "90m"
    update = "90m"
    delete = "90m"
  }

  # Fail at plan time rather than partway into a 60-minute create that cannot
  # be cancelled. Without this, an apply with looker_enabled = true but no
  # TF_VAR_looker_oauth_* exported (CI, or a teammate's shell) reaches the API
  # with empty credentials and consumes trial quota on an instance nobody can
  # sign in to — which provider 5.x then cannot destroy, having no
  # deletion_policy argument.
  lifecycle {
    precondition {
      condition     = length(var.oauth_client_id) > 0 && length(var.oauth_client_secret) > 0
      error_message = "looker_enabled is true but the OAuth credentials are empty. Export TF_VAR_looker_oauth_client_id and TF_VAR_looker_oauth_client_secret (see infra/modules/looker/README-prereqs.md), or set looker_enabled = false."
    }
  }
}
