output "looker_uri" {
  description = "URL of the Looker instance; also the base for the OAuth redirect URI"
  value       = google_looker_instance.this.looker_uri
}

output "looker_version" {
  description = "Looker version running on the instance"
  value       = google_looker_instance.this.looker_version
}

output "egress_public_ip" {
  description = "Public IP the instance egresses from (allowlist this on external data sources)"
  value       = google_looker_instance.this.egress_public_ip
}

output "bq_service_account" {
  description = "Service account to configure in the Looker BigQuery connection"
  value       = google_service_account.looker_bq.email
}
