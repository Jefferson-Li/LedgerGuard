# Runbook

Commands assume region `us-central1` and the resource names Terraform creates. Replace the project id. None of these commands have been executed against a live project in this scaffold.

## See what is running

```bash
gcloud run services list --region us-central1
gcloud run services describe ap-orchestrator --region us-central1
gcloud run revisions list --service matching-agent --region us-central1
```

## Logs

```bash
gcloud run services logs read matching-agent --region us-central1 --limit 50
gcloud beta run services logs tail invoice-mcp --region us-central1
```

Model Armor matches, once sanitize logging is on and a call has been made:

```bash
gcloud logging read \
  'resource.type="modelarmor.googleapis.com/Template" AND jsonPayload.filterMatchState="MATCH_FOUND"' \
  --freshness=1h --limit=20 --format=json
```

The metric `ledgerguard_model_armor_matches` uses that filter. The email policy is created only when `alert_email` is set, and it pages when the metric is greater than 20 in five minutes. `ledgerguard_model_armor_failures` looks for `jsonPayload.invocationResult` of `PARTIAL` or `FAILURE`. Confirm that path against a real log before trusting a zero.

Cloud Trace is not given a dashboard here. If the runtime exports spans, use Trace Explorer in the console. There is no useful CLI equivalent in this runbook.

## Roll back a revision

```bash
gcloud run revisions list --service matching-agent --region us-central1
gcloud run services update-traffic matching-agent \
  --region us-central1 \
  --to-revisions PREVIOUS_REVISION=100
```

Repeat for each service that moved. Terraform is set to ignore image, env, and traffic, so a later apply should not force the old image back. If an apply does rewrite the service, the provider may still send a full body; the deploy workflow sets `AGENT_URL` again after apply. Check the matching agent card URL after any apply.

## Deploy identity

The GitHub deployer is `ledgerguard-deployer`. It is granted broad project roles so one apply can create services, IAM, and templates. That is wider than a runtime service account. Do not use it as a Cloud Run runtime account.

Runtime accounts are `ledgerguard-erp`, `ledgerguard-invoice`, `ledgerguard-matching`, and `ledgerguard-orch`. `ledgerguard-sdp` is reserved for the batch job that is not implemented.

## Stop the billable resources

```bash
./scripts/teardown.sh --yes
```

That runs `terraform destroy` in `infra/envs/dev`. Buckets are `force_destroy`. The state bucket is not in the Terraform configuration; delete it separately if you are finished:

```bash
gcloud storage rm -r gs://PROJECT_ID-tfstate
```

The next day, check Billing reports. Budget settings are not the same thing as spend.
