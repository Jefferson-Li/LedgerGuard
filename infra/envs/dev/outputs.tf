output "artifact_registry" {
  description = "Docker repository the deploy workflow pushes to."
  value       = google_artifact_registry_repository.ledgerguard.id
}

output "prompt_template" {
  description = "Model Armor prompt template."
  value       = module.armor.prompt_template
}

output "response_template" {
  description = "Model Armor response template."
  value       = module.armor.response_template
}

output "erp_uri" {
  description = "erp-mcp URI."
  value       = module.erp.uri
}

output "invoice_uri" {
  description = "invoice-mcp URI."
  value       = module.invoice.uri
}

output "matching_uri" {
  description = "matching-agent URI. Use this as AGENT_URL after the first deploy."
  value       = module.matching.uri
}

output "orchestrator_uri" {
  description = "ap-orchestrator URI."
  value       = module.orchestrator.uri
}

output "deployer_email" {
  description = "GitHub Actions deployer service account."
  value       = module.wif.deployer_email
}

output "workload_identity_provider" {
  description = "WIF provider. Empty until github_repository is set."
  value       = module.wif.workload_identity_provider
}

output "raw_bucket" {
  description = "Raw invoice bucket. invoice-mcp is not granted access."
  value       = google_storage_bucket.raw.name
}

output "clean_bucket" {
  description = "Clean invoice bucket. The de-identify job that fills it is not implemented."
  value       = google_storage_bucket.clean.name
}
