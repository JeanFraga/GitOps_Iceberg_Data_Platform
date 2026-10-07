variable "project_id" {
  description = "GCP project the service accounts live in"
  type        = string
}

variable "impersonators" {
  description = "Principals (e.g. user:owner@example.com) allowed to impersonate the deploy and runtime SAs"
  type        = list(string)
}
