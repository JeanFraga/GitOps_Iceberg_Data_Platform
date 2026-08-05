output "iceberg_warehouse_bucket" {
  description = "Name of the GCS bucket used as the Iceberg warehouse"
  value       = google_storage_bucket.iceberg_warehouse.name
}

output "bq_dataset_id" {
  description = "BigQuery dataset ID for the Gold layer"
  value       = google_bigquery_dataset.iceberg_dataset.dataset_id
}

output "silver_dataset_id" {
  description = "BigQuery dataset ID for the Silver BigLake external table"
  value       = google_bigquery_dataset.silver_dataset.dataset_id
}

output "bq_connection_id" {
  description = "BigQuery BigLake connection ID"
  value       = google_bigquery_connection.gcs_connection.connection_id
}

output "bq_connection_service_account" {
  description = "Service account email created by the BigLake connection"
  value       = google_bigquery_connection.gcs_connection.cloud_resource[0].service_account_id
}
