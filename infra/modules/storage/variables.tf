variable "project_id" {
  description = "GCP project; the landing bucket is named <project_id>-landing"
  type        = string
}

variable "region" {
  description = "Bucket location, from the resolved profile"
  type        = string
}

variable "runtime_member" {
  description = "IAM member of the runtime SA (create + read on landing, no delete)"
  type        = string
}
