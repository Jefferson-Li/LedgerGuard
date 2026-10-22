# Deployment and testing

This is the operator guide for the scaffold. Commands are the ones the workflows and scripts actually run. A GCP project with billing is required for Gemini and Model Armor. The console is optional. Offline unit tests need neither.

This environment validated `pytest`, `terraform fmt` / `validate`, and `docker compose config`. It did not apply Terraform, call Model Armor, or build the images.

## What needs what

| Step | Offline | GCP | Console |
| --- | --- | --- | --- |
| `pytest` unit tests, Model Armor and Gemini not called | Yes | No | No |
| Agent-card and `/health` contract tests | Compose only. Importing the agents does not call the cloud. | No | No |
| `docker compose up` and a real `adk web` conversation | No | Yes. ADC calls Gemini and Model Armor. | No |
| `adk eval`, live red-team | No | Yes | No |
| Terraform, Cloud Run, logs, teardown | No | Yes | No. The console is only a different view. |

## 0. Prepare a project

1. Create a project and link billing.

   ```bash
   gcloud projects create PROJECT_ID
   gcloud billing projects link PROJECT_ID --billing-account=BILLING_ACCOUNT_ID
   gcloud config set project PROJECT_ID
   ```

2. Install the Cloud SDK, Docker Engine with Compose v2, uv, and Terraform 1.6 or newer. The CI Terraform job uses `hashicorp/setup-terraform` and tflint v0.55.1. Log tailing needs `gcloud components install beta`.

3. Log in twice. `gcloud auth login` is for the CLI. `gcloud auth application-default login` is the file the containers mount. Then set a quota project:

   ```bash
   gcloud auth application-default set-quota-project PROJECT_ID
   ```

   On Windows the ADC file is `%APPDATA%\gcloud\application_default_credentials.json`.

4. You can enable APIs yourself, or let Terraform enable them. The configuration turns on Cloud Run, Artifact Registry, Vertex AI, Model Armor, Secret Manager, Sensitive Data Protection, Storage, Firestore, IAM, IAM Credentials, Trace, Logging, Monitoring, Cloud Build, and Cloud Billing Budgets.

5. Templates. Terraform creates `ledgerguard-prompt` and `ledgerguard-response` in `var.region` (default `us-central1`). The prompt template has no SDP filter. The response template uses the advanced SDP inspect and de-identify templates, and the Model Armor service agent is granted `roles/dlp.user` and `roles/dlp.reader`.

   A one-template `gcloud` shortcut is possible and is what the Model Armor codelab does. This repo's services expect the two resource names in `MODEL_ARMOR_PROMPT_TEMPLATE` and `MODEL_ARMOR_RESPONSE_TEMPLATE`. If you create a template by hand, set the regional endpoint first:

   ```bash
   gcloud config set api_endpoint_overrides/modelarmor \
     "https://modelarmor.us-central1.rep.googleapis.com/"
   ```

   The client in `invoice-mcp` sets `api_endpoint` to `modelarmor.{location}.rep.googleapis.com`. The global endpoint cannot sanitize.

6. Copy `.env.example` to `.env` for `uv run`, and `compose.env.example` to `compose.env` for containers. Both names are gitignored. Do not put secrets in them. Leave `MODEL_ARMOR_ALLOW_UNSCREENED` false unless you are deliberately reading synthetic invoices with no screening.

## 1. Run locally

`scripts/run_local.sh` refuses to start unless the ADC file exists, then runs `docker compose up --build`. The compose file mounts that file read-only at `/tmp/keys/adc.json` and sets `GOOGLE_APPLICATION_CREDENTIALS`. It does not use a service account key.

```bash
./scripts/run_local.sh
```

- UI: `http://localhost:8082` (`adk web`). Choose `ap_orchestrator`.
- Agent card: `curl http://localhost:8081/.well-known/agent-card.json`. The card interface URL is `http://matching-agent:8081` on the Docker network. That is expected.
- Deterministic report, no Gemini: `uv run python scripts/run_all_invoices.py`. Nine invoices have fixed match results. `INV-1010` is quarantined by the marker stand-in in that script. A real Model Armor verdict requires the running `invoice-mcp` with a template.
- Offline tests: `uv run pytest`.
- Compose contracts, while the stack is up: `LEDGERGUARD_INTEGRATION=1 uv run pytest tests/integration`. These hit `/health` and the agent card. They do not call Gemini.
- Draft eval, needs GCP and will compare against placeholder answers: `uv run adk eval services/ap_orchestrator evals/ap.evalset.json`. Do not treat the result as a score until the evalset is re-recorded.
- Red-team: `uv run python security/run_redteam.py --mode offline` does not call Model Armor. `--base-url` is accepted and ignored; the runner screens text, it does not drive the chat UI. `--mode live` calls Model Armor for attacks marked `live: call` and needs `MODEL_ARMOR_PROMPT_TEMPLATE`.
- Stop: `docker compose down`.

CI's compose job writes `{}` to the ADC path when the file is missing so the bind mount is a file. That file is not a credential.

## 2. Deploy to GCP

1. State bucket, once, outside Terraform:

   ```bash
   gcloud storage buckets create gs://PROJECT_ID-tfstate \
     --location=us-central1 --uniform-bucket-level-access
   ```

2. First apply, from a machine that already has permission. The GitHub workflow cannot do this until Workload Identity exists.

   ```bash
   cd infra/envs/dev
   terraform init -backend-config="bucket=PROJECT_ID-tfstate"
   terraform plan -out=tfplan
   terraform apply tfplan
   ```

   Set `TF_VAR_project_id`, `TF_VAR_region`, and `TF_VAR_github_repository` (`owner/name`). Optional: `TF_VAR_billing_account_id`, `TF_VAR_alert_email`, `TF_VAR_operator_members` (for example `["user:you@example.com"]`) so you can invoke the private services.

   This creates the Artifact Registry repository `ledgerguard` (immutable tags), four Cloud Run services on the public `hello` image, service accounts, invoker bindings between them, buckets, an empty Secret Manager secret, Firestore in the same region, both Model Armor templates, log metrics, the Workload Identity pool `ledgerguard-github`, and the budget when a billing account is set.

3. Copy Terraform outputs into GitHub. The workflow reads:

   | Name | Kind | Purpose |
   | --- | --- | --- |
   | `GCP_PROJECT_ID` | variable | Project |
   | `TF_STATE_BUCKET` | variable | State bucket name, without `gs://` |
   | `GCP_REGION` | variable | Optional, default `us-central1` |
   | `BILLING_ACCOUNT_ID` | variable | Optional budget |
   | `ALERT_EMAIL` | variable | Optional alert |
   | `RUN_LIVE_REDTEAM` | variable | Set to `true` to call Model Armor from CI |
   | `RUN_ADK_EVAL` | variable | Set to `true` to run the draft eval |
   | `MODEL_ARMOR_PROMPT_TEMPLATE` | variable | Full resource name for the live red-team |
   | `WIF_PROVIDER` | secret | `projects/PROJECT_NUMBER/locations/global/workloadIdentityPools/ledgerguard-github/providers/github` |
   | `WIF_SERVICE_ACCOUNT` | secret | `ledgerguard-deployer@PROJECT_ID.iam.gserviceaccount.com` |

   Until those four required values exist, `ci.yml` skips the plan and `deploy.yml` skips the deploy. The push still goes green on the offline jobs.

4. After the secrets exist, a push to `main` runs `deploy.yml`: Terraform apply, `docker build --platform linux/amd64` for the four services, push to `REGION-docker.pkg.dev/PROJECT/ledgerguard/NAME:SHA`, `gcloud run deploy --no-traffic --tag green`, set `AGENT_URL` on `matching-agent` to that service's own URL, smoke-test with `gcloud auth print-identity-token --audiences=TAG_URL`, then `update-traffic --to-tags green=100`.

   Order is the two MCP services, then matching, then the orchestrator. The orchestrator smoke requests `/` because `adk web` is not given a `/health` route in this scaffold. The other three use `/health`, and matching also fetches the agent card.

5. Manual equivalent for one service:

   ```bash
   gcloud auth configure-docker us-central1-docker.pkg.dev
   docker build --platform linux/amd64 \
     -f services/matching_agent/Dockerfile \
     -t us-central1-docker.pkg.dev/PROJECT_ID/ledgerguard/matching-agent:GIT_SHA .
   docker push us-central1-docker.pkg.dev/PROJECT_ID/ledgerguard/matching-agent:GIT_SHA
   gcloud run deploy matching-agent \
     --image us-central1-docker.pkg.dev/PROJECT_ID/ledgerguard/matching-agent:GIT_SHA \
     --region us-central1 --no-traffic --tag green \
     --update-env-vars AGENT_URL=https://MATCHING_HOST
   ```

   Build with `--platform linux/amd64` on Apple Silicon. Processes must listen on `$PORT`.

6. Shift traffic only after the smoke test:

   ```bash
   gcloud run services update-traffic matching-agent \
     --region us-central1 --to-tags green=100
   ```

7. Roll back:

   ```bash
   gcloud run revisions list --service matching-agent --region us-central1
   gcloud run services update-traffic matching-agent \
     --region us-central1 --to-revisions PREVIOUS=100
   ```

Terraform ignores `template[0].containers[0].image`, `template[0].containers[0].env`, `traffic`, `client`, and `client_version`. Image and traffic belong to the deploy workflow. Env is ignored so a later apply does not wipe `AGENT_URL`. The matching service cannot read its own URI inside the same resource, which is why the workflow sets that variable after the service exists.

`to_a2a` always includes the port in the card URL. Cloud Run `https` URLs are advertised with `:443`. Confirm the card on the first deploy.

## 3. Looking at the system

| Question | CLI |
| --- | --- |
| Revisions and traffic | `gcloud run services describe ap-orchestrator --region us-central1` |
| Application logs | `gcloud run services logs read matching-agent --region us-central1 --limit 50` |
| Tail | `gcloud beta run services logs tail invoice-mcp --region us-central1` |
| Model Armor matches | The logging read in `docs/runbook.md` |
| Template | `gcloud model-armor templates describe ledgerguard-prompt --location=us-central1` |
| Trace waterfall | Trace Explorer. No CLI in this guide. |
| Budget configuration | `gcloud billing budgets list --billing-account=BILLING_ACCOUNT_ID` |
| Actual spend | Billing reports. They lag. A budget is not a spend figure. |

## 4. Tear down

```bash
./scripts/teardown.sh --yes
```

`terraform destroy` removes the services, templates, and buckets (`force_destroy` is set). Delete a hand-created template separately. Delete the state bucket only when you are done with the environment. `gcloud run services list`, `gcloud artifacts repositories list`, `gcloud storage ls`, and `gcloud secrets list` should be empty of LedgerGuard resources afterwards. Check Billing reports the next day. Deleting the project is the way to stop an account you will not reuse.

## 5. Failures that show up often

| Symptom | What to check |
| --- | --- |
| `DefaultCredentialsError` | ADC login was not run, or `GOOGLE_APPLICATION_CREDENTIALS` does not match the mount. |
| 403 asking for a quota project | `gcloud auth application-default set-quota-project PROJECT_ID`. |
| `SERVICE_DISABLED` | Enable the API named in the error and wait a few minutes. |
| Model Armor `PERMISSION_DENIED` for an Owner | The client or gcloud is not using the regional endpoint. |
| Region rejected | Sydney is unsupported. Melbourne is limited. This stack defaults to `us-central1`. See ADR 0001. |
| 403 between services | The caller service account lacks `roles/run.invoker`, or the ID-token audience is not the target origin. |
| Agent card advertises localhost or the wrong port | `AGENT_URL` was not set after the first deploy, or the client rejected `:443`. |
| `exec format error` or the container never listens | Rebuild `linux/amd64` and listen on `$PORT`. Read `gcloud run services logs read`. |
| SDP errors from the response template | The Model Armor service agent needs `roles/dlp.user` and `roles/dlp.reader`. Terraform grants both. |
| Every invoice is quarantined with `screening_failed` | No template is configured and `MODEL_ARMOR_ALLOW_UNSCREENED` is not set. That is the fail-closed default. |
| CI is green but nothing deployed | `WIF_PROVIDER`, `WIF_SERVICE_ACCOUNT`, `GCP_PROJECT_ID`, or `TF_STATE_BUCKET` is unset. The cloud jobs skip on purpose. |
