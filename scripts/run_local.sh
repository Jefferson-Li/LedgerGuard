#!/usr/bin/env bash
# Start the four services with Docker Compose. Requires the Docker daemon and,
# for a real Model Armor / Gemini conversation, Application Default Credentials.
set -euo pipefail
cd "$(dirname "$0")/.."

COMPOSE_MIN="2.17.0"

if ! command -v docker >/dev/null 2>&1; then
  echo "docker is not installed" >&2
  exit 1
fi

if ! docker compose version >/dev/null 2>&1; then
  echo "docker compose v2 is required" >&2
  exit 1
fi

docker compose version

compose_at_least() {
  local actual="$1"
  local minimum="$2"
  local a1 a2 a3 m1 m2 m3
  IFS=. read -r a1 a2 a3 <<EOF
${actual}
EOF
  IFS=. read -r m1 m2 m3 <<EOF
${minimum}
EOF
  a1="${a1:-0}"
  a2="${a2:-0}"
  a3="${a3:-0}"
  m1="${m1:-0}"
  m2="${m2:-0}"
  m3="${m3:-0}"
  a1="${a1%%[^0-9]*}"
  a2="${a2%%[^0-9]*}"
  a3="${a3%%[^0-9]*}"
  if [ "${a1:-0}" -gt "${m1:-0}" ]; then
    return 0
  fi
  if [ "${a1:-0}" -lt "${m1:-0}" ]; then
    return 1
  fi
  if [ "${a2:-0}" -gt "${m2:-0}" ]; then
    return 0
  fi
  if [ "${a2:-0}" -lt "${m2:-0}" ]; then
    return 1
  fi
  if [ "${a3:-0}" -ge "${m3:-0}" ]; then
    return 0
  fi
  return 1
}

compose_short="$(docker compose version --short 2>/dev/null || true)"
compose_short="${compose_short#v}"
compose_short="$(printf '%s' "${compose_short}" | sed 's/[^0-9.].*$//')"
if ! compose_at_least "${compose_short}" "${COMPOSE_MIN}"; then
  echo "Docker Compose ${compose_short:-unknown} is older than ${COMPOSE_MIN}. This compose file needs Docker Compose ${COMPOSE_MIN} or newer." >&2
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
case "${adc}" in
  /*) ;;
  *)
    echo "ADC_PATH must be an absolute path. Got: ${adc}" >&2
    exit 1
    ;;
esac
export ADC_PATH="${adc}"

if [[ ! -f "${ADC_PATH}" ]]; then
  echo "ADC file not found at ${ADC_PATH}." >&2
  echo "Run: gcloud auth application-default login" >&2
  echo "Compose mounts that file read-only. It does not use a service account key." >&2
  exit 1
fi

if [[ -f compose.env ]]; then
  while IFS= read -r line || [[ -n "${line}" ]]; do
    case "${line}" in
      ''|\#*) continue ;;
    esac
    line="${line#export }"
    key="${line%%=*}"
    val="${line#*=}"
    if [[ "${key}" == "${line}" || "${key}" == "ADC_PATH" ]]; then
      continue
    fi
    case "${key}" in
      [A-Za-z_]*) ;;
      *) continue ;;
    esac
    case "${val}" in
      \"*\") val="${val#\"}"; val="${val%\"}" ;;
      \'*\') val="${val#\'}"; val="${val%\'}" ;;
    esac
    export "${key}=${val}"
  done < compose.env
elif [[ -f compose.env.example ]]; then
  echo "compose.env is optional. Copy compose.env.example if you want container-only variables."
fi

docker compose up --build "$@"
