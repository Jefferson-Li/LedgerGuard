#!/usr/bin/env bash
# Full offline check suite. Runs inside the test-runner image.
# The checkout is bind-mounted at /workspace. Tools come from the image.
set -u

cd /workspace

export UV_PROJECT_ENVIRONMENT="${UV_PROJECT_ENVIRONMENT:-/opt/venv}"
export PYTHONDONTWRITEBYTECODE=1
export PYTHONPYCACHEPREFIX="${PYTHONPYCACHEPREFIX:-/tmp/pycache}"
export RUFF_CACHE_DIR="${RUFF_CACHE_DIR:-/tmp/ruff-cache}"
# Published host ports are the pytest defaults. On the compose network the
# services listen on their container ports.
export ERP_HEALTH_URL="${ERP_HEALTH_URL:-http://erp-mcp:8080/health}"
export INVOICE_HEALTH_URL="${INVOICE_HEALTH_URL:-http://invoice-mcp:8080/health}"
export MATCHING_CARD_URL="${MATCHING_CARD_URL:-http://matching-agent:8081/.well-known/agent-card.json}"

failed=0
results=()

run_step() {
  local name="$1"
  shift
  echo
  echo "========== ${name} =========="
  if "$@"; then
    echo "PASS  ${name}"
    results+=("PASS  ${name}")
  else
    echo "FAIL  ${name}"
    results+=("FAIL  ${name}")
    failed=1
  fi
}

run_step "ruff check" ruff check .
run_step "ruff format --check" ruff format --check .

# The contract tests run as their own step, after the services are healthy.
run_step "pytest" env -u LEDGERGUARD_INTEGRATION pytest -p no:cacheprovider

run_step "offline red-team" python security/run_redteam.py --mode offline
run_step "run_all_invoices" python scripts/run_all_invoices.py

triage_step() {
  local dir status
  dir="$(mktemp -d)"
  LEDGERGUARD_TRIAGE_PLAN="${dir}/triage-plan.json" \
    LEDGERGUARD_TRIAGE_STORE="${dir}/triage-decisions.json" \
    LEDGERGUARD_TRIAGE_CACHE="${dir}/cache" \
    LEDGERGUARD_TRIAGE_JUDGE=stub \
    python scripts/triage.py plan \
    && LEDGERGUARD_TRIAGE_PLAN="${dir}/triage-plan.json" \
      LEDGERGUARD_TRIAGE_STORE="${dir}/triage-decisions.json" \
      LEDGERGUARD_TRIAGE_CACHE="${dir}/cache" \
      LEDGERGUARD_TRIAGE_JUDGE=stub \
      python scripts/triage.py apply \
    && LEDGERGUARD_TRIAGE_PLAN="${dir}/triage-plan.json" \
      LEDGERGUARD_TRIAGE_STORE="${dir}/triage-decisions.json" \
      LEDGERGUARD_TRIAGE_CACHE="${dir}/cache" \
      LEDGERGUARD_TRIAGE_JUDGE=stub \
      python scripts/triage.py reset -yes
  status=$?
  rm -rf "${dir}"
  return "${status}"
}

run_step "triage plan/apply/reset -yes" triage_step

run_step "integration contracts" \
  env LEDGERGUARD_INTEGRATION=1 pytest -p no:cacheprovider tests/integration

copy_tree() {
  local dir="$1"
  cp -a infra "${dir}/infra"
  cp -a .tflint.hcl "${dir}/.tflint.hcl"
}

terraform_fmt() {
  local dir status
  dir="$(mktemp -d)"
  copy_tree "${dir}"
  (cd "${dir}/infra" && terraform fmt -check -recursive)
  status=$?
  rm -rf "${dir}"
  return "${status}"
}

terraform_validate() {
  local dir status
  dir="$(mktemp -d)"
  copy_tree "${dir}"
  (
    cd "${dir}/infra/envs/dev"
    terraform init -backend=false -input=false
    terraform validate
  )
  status=$?
  rm -rf "${dir}"
  return "${status}"
}

tflint_step() {
  local dir status
  dir="$(mktemp -d)"
  copy_tree "${dir}"
  (
    cd "${dir}"
    tflint --init
    tflint --recursive --config "${dir}/.tflint.hcl"
  )
  status=$?
  rm -rf "${dir}"
  return "${status}"
}

run_step "terraform fmt -check" terraform_fmt
run_step "terraform init and validate" terraform_validate
run_step "tflint" tflint_step
run_step "checkov" checkov -d infra --framework terraform --quiet

echo
echo "========== summary =========="
for line in "${results[@]}"; do
  echo "${line}"
done
if [[ "${failed}" -eq 0 ]]; then
  echo "PASS  all checks"
  exit 0
fi
echo "FAIL  one or more checks"
exit 1
