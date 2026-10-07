#!/usr/bin/env bash
# post-create.sh – runs once after the dev container is created
# (wired up via postCreateCommand in devcontainer.json)
set -euo pipefail

echo "==> Verifying toolchain …"
terraform -version | head -1
gcloud --version | head -1
uv --version
node --version
claude --version

echo "==> Syncing Python project (uv.lock)"
uv sync --frozen

echo ""
echo "Dev container ready."
echo "See README.md for the quick-start and run 'make help' for common tasks."
