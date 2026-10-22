#!/usr/bin/env bash
# One command for a machine that has only Docker Desktop with Compose v2.
# Safe to run from macOS zsh or bash: ./scripts/docker-test.sh
# Bash 3.2 (the macOS /bin/bash) is enough. The checks themselves run in Linux.
set -u

cd "$(dirname "$0")/.."

if ! command -v docker >/dev/null 2>&1; then
  echo "docker is not installed" >&2
  exit 1
fi

if ! docker compose version >/dev/null 2>&1; then
  echo "docker compose v2 is required" >&2
  exit 1
fi

if [[ -n "${ADC_PATH:-}" ]]; then
  adc="${ADC_PATH}"
else
  if [[ -z "${HOME:-}" ]]; then
    echo "Set HOME or ADC_PATH so Compose can mount Application Default Credentials." >&2
    exit 1
  fi
  adc="${HOME}/.config/gcloud/application_default_credentials.json"
fi

# Placeholder only. Never replace a real credential file or an existing symlink.
if [[ ! -e "${adc}" && ! -L "${adc}" ]]; then
  mkdir -p "$(dirname "${adc}")"
  printf '%s\n' '{}' > "${adc}"
  echo "Wrote a placeholder ADC file at ${adc}. It is not a credential."
fi

cleanup() {
  local code=$?
  if [[ "${code}" -ne 0 ]]; then
    docker compose --profile test logs --no-color || true
  fi
  docker compose --profile test down || true
  exit "${code}"
}
trap cleanup EXIT

docker compose --profile test up --build --abort-on-container-exit --exit-code-from test-runner
