#!/usr/bin/env bash
# One command for a machine that has only Docker Desktop with Compose v2.
# Safe to run from macOS zsh or bash: ./scripts/docker-test.sh
# Bash 3.2 (the macOS /bin/bash) is enough. The checks themselves run in Linux.
set -u

cd "$(dirname "$0")/.."

# LedgerGuard's compose file parses on Compose 2.17. Nested defaults do not.
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

# Absolute path. Compose is given ADC_PATH and does not apply its own default.
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
    adc_dir="$(dirname "${adc}")"
    adc_base="$(basename "${adc}")"
    mkdir -p "${adc_dir}"
    adc="$(cd "${adc_dir}" && pwd)/${adc_base}"
    ;;
esac
export ADC_PATH="${adc}"

# Local overrides. Do not let this file replace the ADC path chosen above.
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
fi

# Placeholder only. Never replace a real credential file or an existing symlink.
if [[ ! -e "${ADC_PATH}" && ! -L "${ADC_PATH}" ]]; then
  mkdir -p "$(dirname "${ADC_PATH}")"
  printf '%s\n' '{}' > "${ADC_PATH}"
  echo "Wrote a placeholder ADC file at ${ADC_PATH}. It is not a credential."
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
