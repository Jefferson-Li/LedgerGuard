output "match_metric" {
  description = "Log-based metric name for Model Armor MATCH_FOUND events."
  value       = google_logging_metric.armor_matches.name
}

output "notification_channel" {
  description = "Email notification channel, if configured."
  value       = try(google_monitoring_notification_channel.email[0].id, "")
}
