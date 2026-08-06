####################################################################
# Project manifest.
#
# Must live at the root of the LookML project directory (Looker
# resolves `manifest.lkml` from the repo root it is connected to).
#
# Everything environment-specific is a constant so the project can be
# repointed at another GCP project or dataset by editing this file
# alone — no view or model edits required.
####################################################################

project_name: "nyc_taxi_gold"

# Name of the BigQuery connection configured in Looker under
# Admin > Database > Connections. Looker connections are created in the
# UI (or via the Looker API), not in LookML, so this is the one value
# that must be kept in sync by hand.
constant: connection_name {
  value: "nyc_taxi_bigquery"
}

# Must match infra/environments/dev TF_VAR_project_id.
constant: gcp_project_id {
  value: "gitops-iceberg-data-platform"
}

# Must match bq_dataset_id in infra/modules/bq_iceberg/variables.tf
# and DBT_DATASET in src/dbt_project/profiles.yml.
constant: gold_dataset {
  value: "gold_star_schema"
}
