output "inspect_template" {
  description = "DLP inspect template id."
  value       = google_data_loss_prevention_inspect_template.invoices.id
}

output "deidentify_template" {
  description = "DLP de-identify template id."
  value       = google_data_loss_prevention_deidentify_template.invoices.id
}
