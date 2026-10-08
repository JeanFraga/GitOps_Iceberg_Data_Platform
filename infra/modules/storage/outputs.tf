output "landing_bucket" {
  value = google_storage_bucket.landing.name
}

output "warehouse_bucket" {
  value = google_storage_bucket.warehouse.name
}

output "iceberg_catalog" {
  value = google_biglake_iceberg_catalog.warehouse.name
}
