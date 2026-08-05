#!/usr/bin/env bash
# post-create.sh – runs once after the dev container is created
# (wired up via postCreateCommand in devcontainer.json)
set -euo pipefail

echo "==> Verifying toolchain …"
python -c "import pyspark; print('PySpark', pyspark.__version__)"
dbt --version
terraform -version | head -1
gcloud --version | head -1

echo ""
echo "Dev container ready."
echo "See README.md for the quick-start and run 'make help' for common tasks."
