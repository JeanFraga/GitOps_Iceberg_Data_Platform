output "steward_dataset_id" {
  value = google_bigquery_dataset.steward.dataset_id
}

output "mpi_eval_dataset_id" {
  value = google_bigquery_dataset.mpi_eval.dataset_id
}

output "table_ids" {
  value = sort(keys(google_bigquery_table.this))
}
