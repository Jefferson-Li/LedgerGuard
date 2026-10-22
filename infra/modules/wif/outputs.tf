output "deployer_email" {
  description = "Service account GitHub Actions impersonates."
  value       = google_service_account.deployer.email
}

output "workload_identity_provider" {
  description = "Full Workload Identity provider resource name. Empty until github_repository is set."
  value       = try(google_iam_workload_identity_pool_provider.github[0].name, "")
}
