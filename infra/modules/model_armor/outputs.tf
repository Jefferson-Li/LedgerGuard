output "prompt_template" {
  description = "Model Armor template for user prompts and untrusted documents."
  value       = google_model_armor_template.prompt.id
}

output "response_template" {
  description = "Model Armor template for model responses, including SDP de-identify."
  value       = google_model_armor_template.response.id
}
