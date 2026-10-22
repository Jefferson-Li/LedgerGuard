# Contributing

LedgerGuard is a learning project. Changes should keep the offline tests honest and the unfinished parts labelled as unfinished.

## Setup

```bash
uv sync --all-packages --group dev
uv run ruff check .
uv run ruff format --check .
uv run pytest
uv run python security/run_redteam.py --mode offline
```

A machine with only Docker Desktop (Compose v2) can run the same offline suite, plus the compose contracts and the Terraform checks, with `./scripts/docker-test.sh` or `make test`. That command does not install uv, Python, Terraform, tflint, or checkov on the host.

Terraform:

```bash
terraform fmt -check -recursive infra
cd infra/envs/dev
terraform init -backend=false -input=false
terraform validate
```

`docker compose config` should succeed. A conversation through `adk web` needs a GCP project and Application Default Credentials. Do not commit `.env`, `compose.env`, credential files, or Terraform state.

## What to keep true

- Money stays in `services/matching_agent/rules.py`. Do not move GST or tolerances into a prompt. Exception triage may cite only labels from `policy/ap-policy.md`. An unknown label is low confidence and is escalated. The model does not set variance, GST, or tolerance.
- `invoice-mcp` withholds the document body when any paragraph matches or when screening fails. Do not return the raw invoice on a match.
- Do not set `MODEL_ARMOR_ALLOW_UNSCREENED` in Cloud Run or in the deploy workflow.
- Offline tests must not call Gemini or Model Armor. Live checks belong behind the existing CI flags.
- If a feature is not implemented, say so in the README and in `docs/`. Do not add counts, prices, or "blocked every attack" claims that the tests did not measure.
- The English README is the source text. `README.zh-TW.md` should stay a translation of it, including the work-in-progress notes.

## Pull requests

`ci.yml` runs ruff, pytest, the offline red-team, Terraform fmt/validate, tflint, and checkov without cloud credentials. The compose job runs `scripts/docker-test.sh`, the same command as a local Docker-only run. Cloud plan, live red-team, and `adk eval` run only when the repository variables and Workload Identity secrets described in `docs/deployment-and-testing.md` are present.
