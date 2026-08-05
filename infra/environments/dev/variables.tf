variable "project_id" {
  description = "GCP project ID"
  type        = string
}

variable "region" {
  description = "GCP region"
  type        = string
  default     = "us-central1"
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
