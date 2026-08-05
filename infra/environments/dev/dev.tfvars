# dev.tfvars  – do NOT commit real credentials
# Sensitive values (project_id, pipeline_service_account) are supplied via
# TF_VAR_project_id and TF_VAR_pipeline_service_account environment variables
# set from GitHub Actions secrets (GCP_PROJECT_ID, PIPELINE_SERVICE_ACCOUNT).
region        = "us-central1"
force_destroy = true
