output "composer_sa_email" {
  description = "Service account the Composer environment runs as"
  value       = google_service_account.composer.email
}

output "dag_gcs_prefix" {
  description = "GCS prefix (gs://bucket/dags) where DAGs are synced"
  value       = google_composer_environment.this.config[0].dag_gcs_prefix
}

output "airflow_uri" {
  description = "Airflow web UI URL"
  value       = google_composer_environment.this.config[0].airflow_uri
}
