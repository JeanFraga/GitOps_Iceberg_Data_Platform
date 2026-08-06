variable "project_id" {
  description = "GCP project ID"
  type        = string
}

variable "region" {
  description = "GCP region"
  type        = string
  default     = "us-east1"
}

variable "force_destroy" {
  description = "Allow Terraform to destroy non-empty resources (set true for dev only)"
  type        = bool
  default     = true
}

variable "pipeline_service_account" {
  description = "Service account used by Dataproc Serverless jobs"
  type        = string
  default     = ""
}

variable "composer_enabled" {
  description = "Provision the Cloud Composer environment (bills ~$10-12/day even at the smallest size; disable between testing sessions)"
  type        = bool
  default     = false
}

variable "looker_enabled" {
  description = "Provision the Looker (Google Cloud core) instance for the BI demo. Requires Looker quota on the project and a hand-created OAuth client — see infra/modules/looker/README-prereqs.md. Creation takes ~60 minutes."
  type        = bool
  default     = false
}

variable "looker_oauth_client_id" {
  description = "OAuth 2.0 client ID for Looker sign-in. Supplied via TF_VAR_looker_oauth_client_id; only read when looker_enabled is true."
  type        = string
  default     = ""
}

variable "looker_oauth_client_secret" {
  description = "OAuth 2.0 client secret for Looker sign-in. Supplied via TF_VAR_looker_oauth_client_secret; only read when looker_enabled is true."
  type        = string
  default     = ""
  sensitive   = true
}
