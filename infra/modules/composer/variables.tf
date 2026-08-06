variable "project_id" {
  description = "GCP project ID"
  type        = string
}

variable "region" {
  description = "GCP region for the Composer environment"
  type        = string
  default     = "us-east1"
}

variable "environment_name" {
  description = "Cloud Composer environment name (must match COMPOSER_ENV in .github/workflows/composer-sync.yml)"
  type        = string
  default     = "nyc-taxi-composer"
}

variable "image_version" {
  description = "Composer image alias; composer-3 resolves to the latest supported Airflow 2 build"
  type        = string
  default     = "composer-3-airflow-2"
}

variable "iceberg_warehouse_bucket" {
  description = "Name of the Iceberg warehouse GCS bucket the DAG reads and writes"
  type        = string
}
