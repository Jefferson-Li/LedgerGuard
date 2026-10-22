#!/usr/bin/env bash
# Destroy the dev Terraform stack. Refuses to run unless --yes is passed.
set -euo pipefail
cd "$(dirname "$0")/../infra/envs/dev"

if [[ "${1:-}" != "--yes" ]]; then
  echo "This runs terraform destroy in infra/envs/dev." >&2
  echo "Pass --yes to continue. State bucket and any Model Armor template created outside Terraform are not removed." >&2
  exit 1
fi

terraform destroy
