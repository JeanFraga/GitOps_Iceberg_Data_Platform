# dev.tfvars  – do NOT commit real credentials
# Sensitive values (project_id, pipeline_service_account) are supplied via
# TF_VAR_project_id and TF_VAR_pipeline_service_account environment variables
# set from GitHub Actions secrets (GCP_PROJECT_ID, PIPELINE_SERVICE_ACCOUNT).
region        = "us-east1"
force_destroy = true

# Cost lever: the Composer environment bills continuously; set false and
# apply to destroy it between PoC testing sessions.
composer_enabled = true

# BI demo. Creation takes ~60 minutes and cannot be cancelled. The trial runs
# 30 days and then AUTO-CONVERTS to a paid Standard instance rather than
# expiring — destroy before day 30 to avoid billing. Requires trial quota
# (register at https://cloud.google.com/resources/looker-free-trial) and
# a hand-created OAuth client supplied via TF_VAR_looker_oauth_client_id /
# TF_VAR_looker_oauth_client_secret — see infra/modules/looker/README-prereqs.md.
#
# The looker module carries a precondition that fails the plan if those two
# variables are empty, so an apply without them errors immediately instead of
# provisioning an instance nobody can sign in to.
looker_enabled = true
