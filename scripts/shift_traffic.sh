#!/usr/bin/env bash
# Smoke-test a tagged Cloud Run revision, then shift traffic only on success.
# Usage: scripts/shift_traffic.sh <service> <region> <tag>
set -euo pipefail
cd "$(dirname "$0")/.."

service="${1:?service name}"
region="${2:?region}"
tag="${3:-green}"

python3 - <<PY
import json, os, subprocess, sys
service = "${service}"
region = "${region}"
tag = "${tag}"
raw = subprocess.check_output(
    ["gcloud", "run", "services", "describe", service, "--region", region, "--format=json"],
    text=True,
)
payload = json.loads(raw)
url = ""
for item in payload.get("status", {}).get("traffic", []):
    if item.get("tag") == tag and item.get("url"):
        url = item["url"]
        break
if not url:
    print(f"No URL for tag {tag} on {service}", file=sys.stderr)
    sys.exit(1)
print(url)
PY
url="$(python3 - <<PY
import json, subprocess, sys
service = "${service}"
region = "${region}"
tag = "${tag}"
raw = subprocess.check_output(
    ["gcloud", "run", "services", "describe", service, "--region", region, "--format=json"],
    text=True,
)
payload = json.loads(raw)
for item in payload.get("status", {}).get("traffic", []):
    if item.get("tag") == tag and item.get("url"):
        print(item["url"])
        sys.exit(0)
sys.exit(1)
PY
)"

token="$(gcloud auth print-identity-token)"
export SMOKE_BASE_URL="${url}"
export SMOKE_ID_TOKEN="${token}"
if [[ "${service}" == "matching-agent" ]]; then
  export SMOKE_EXPECT_CARD=1
else
  unset SMOKE_EXPECT_CARD || true
fi

if [[ "${service}" == "ap-orchestrator" ]]; then
  curl --fail-with-body -sS -H "Authorization: Bearer ${token}" "${url}/" >/dev/null
  echo "orchestrator responded at ${url}"
else
  uv run pytest tests/smoke
fi

gcloud run services update-traffic "${service}" --region "${region}" --to-tags "${tag}=100"
echo "shifted ${service} traffic to ${tag}"
