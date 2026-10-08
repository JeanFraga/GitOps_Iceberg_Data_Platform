# Ops, steward and mpi_eval tables (AD-10, AD-16, AD-17, AD-23, AD-24, AD-25).
# One JSON schema per table under schemas/<dataset>.<table>.json; the ops dataset
# itself is owned by the environment and passed in by id.

terraform {
  required_version = ">= 1.16.5"

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = ">= 8.6.0"
    }
  }
}

locals {
  schema_dir = "${path.module}/schemas"
  tables = {
    for f in fileset(local.schema_dir, "*.json") :
    trimsuffix(f, ".json") => {
      dataset = split(".", f)[0]
      table   = split(".", f)[1]
      schema  = file("${local.schema_dir}/${f}")
    }
  }
  # Day partitioning only on these two (column per table).
  partition_field = {
    "ops.run_events"     = "event_at"
    "ops.file_lifecycle" = "recorded_at"
  }
}

resource "google_bigquery_dataset" "steward" {
  project                    = var.project_id
  dataset_id                 = "steward"
  location                   = var.region
  delete_contents_on_destroy = true
}

resource "google_bigquery_dataset" "mpi_eval" {
  project                    = var.project_id
  dataset_id                 = "mpi_eval"
  location                   = var.region
  delete_contents_on_destroy = true
}

locals {
  dataset_ids = {
    ops      = var.ops_dataset_id
    steward  = google_bigquery_dataset.steward.dataset_id
    mpi_eval = google_bigquery_dataset.mpi_eval.dataset_id
  }
}

resource "google_bigquery_table" "this" {
  for_each = local.tables

  project             = var.project_id
  dataset_id          = local.dataset_ids[each.value.dataset]
  table_id            = each.value.table
  schema              = each.value.schema
  deletion_protection = false

  dynamic "time_partitioning" {
    for_each = contains(keys(local.partition_field), each.key) ? [local.partition_field[each.key]] : []
    content {
      type  = "DAY"
      field = time_partitioning.value
    }
  }
}
