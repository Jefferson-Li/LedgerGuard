output "uri" {
  description = "Cloud Run service URI."
  value       = google_cloud_run_v2_service.this.uri
}

output "name" {
  description = "Cloud Run service name."
  value       = google_cloud_run_v2_service.this.name
}

output "service_account_email" {
  description = "Runtime service account email."
  value       = google_service_account.this.email
}
