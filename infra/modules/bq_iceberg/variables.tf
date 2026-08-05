variable "project_id" {
  description = "GCP project ID"
  type        = string
}

variable "region" {
  description = "GCP region for all resources"
  type        = string
  default     = "us-east1"
}

variable "bq_dataset_id" {
  description = "BigQuery dataset ID for the Gold layer"
  type        = string
  default     = "gold_star_schema"
}

variable "silver_dataset_id" {
  description = "BigQuery dataset ID for the Silver BigLake external table (must match SILVER_DATASET in .github/workflows/release.yml)"
  type        = string
  default     = "silver"
}

variable "bq_connection_id" {
  description = "BigQuery BigLake connection ID (must match BQ_CONNECTION_ID in .github/workflows/release.yml)"
  type        = string
  default     = "iceberg-gcs-conn"
}

variable "force_destroy" {
  description = "Allow Terraform to destroy non-empty GCS buckets and BQ datasets"
  type        = bool
  default     = false
}

variable "pipeline_service_account" {
  description = "Service account email used by Dataproc Serverless / PySpark jobs. Leave empty to skip IAM binding."
  type        = string
  default     = ""
}
