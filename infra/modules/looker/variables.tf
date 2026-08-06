variable "project_id" {
  description = "GCP project ID"
  type        = string
}

variable "region" {
  description = "GCP region for the Looker (Google Cloud core) instance"
  type        = string
  default     = "us-east1"
}

variable "instance_name" {
  description = "Looker (Google Cloud core) instance name"
  type        = string
  default     = "nyc-taxi-looker"
}

variable "platform_edition" {
  description = "Looker platform edition. LOOKER_CORE_TRIAL runs 30 days, cannot be extended, and AUTO-CONVERTS to a paid Standard instance rather than expiring — destroy before day 30 to avoid billing. Editions cannot be changed after creation; switching means destroy + recreate. Requires trial quota, which is granted by registering at https://cloud.google.com/resources/looker-free-trial."
  type        = string
  default     = "LOOKER_CORE_TRIAL"

  validation {
    condition = contains([
      "LOOKER_CORE_TRIAL",
      "LOOKER_CORE_STANDARD",
      "LOOKER_CORE_STANDARD_ANNUAL",
      "LOOKER_CORE_ENTERPRISE_ANNUAL",
      "LOOKER_CORE_EMBED_ANNUAL",
    ], var.platform_edition)
    error_message = "platform_edition must be one of the LOOKER_CORE_* values supported by the google provider."
  }
}

# oauth_config is a REQUIRED block on google_looker_instance, and both fields
# inside it are required. The OAuth client itself must be created by hand in
# the console (APIs & Services > Credentials > OAuth client ID, type "Web
# application") — the google provider has no resource for it. See
# README-prereqs.md; the redirect URI depends on the instance URL, so this is
# inherently a two-pass setup.
variable "oauth_client_id" {
  description = "OAuth 2.0 client ID used for Looker instance sign-in"
  type        = string
}

variable "oauth_client_secret" {
  description = "OAuth 2.0 client secret used for Looker instance sign-in"
  type        = string
  sensitive   = true
}

variable "allowed_email_domains" {
  description = "Email domains permitted to sign in to the instance. Empty list omits the admin_settings block entirely."
  type        = list(string)
  default     = []
}

variable "public_ip_enabled" {
  description = "Expose the instance on a public IP. True keeps the PoC reachable without VPC peering; set false only alongside consumer_network/reserved_range."
  type        = bool
  default     = true
}

variable "gold_dataset_id" {
  description = "BigQuery dataset the Looker connection reads (the dbt Gold layer)"
  type        = string
  default     = "gold_star_schema"
}
