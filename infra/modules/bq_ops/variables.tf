variable "project_id" {
  description = "GCP project, from the resolved profile"
  type        = string
}

variable "region" {
  description = "Dataset location, from the resolved profile"
  type        = string
}

variable "ops_dataset_id" {
  description = "Existing ops dataset id (declared in the environment)"
  type        = string
}
