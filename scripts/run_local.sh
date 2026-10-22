#!/usr/bin/env bash
# Start the four services with Docker Compose. Requires the Docker daemon and,
# for a real Model Armor / Gemini conversation, Application Default Credentials.
set -euo pipefail
cd "$(dirname "$0")/.."

if ! command -v docker >/dev/null 2>&1; then
  echo "docker is not installed" >&2
  exit 1
fi

adc="${ADC_PATH:-${HOME}/.config/gcloud/application_default_credentials.json}"
if [[ ! -f "${adc}" ]]; then
  echo "ADC file not found at ${adc}." >&2
  echo "Run: gcloud auth application-default login" >&2
  echo "Compose mounts that file read-only. It does not use a service account key." >&2
  exit 1
fi

if [[ ! -f compose.env && -f compose.env.example ]]; then
  echo "compose.env is optional. Copy compose.env.example if you want container-only variables."
fi

docker compose up --build "$@"
