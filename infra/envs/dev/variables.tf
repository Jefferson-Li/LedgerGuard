variable "project_id" {
  type        = string
  description = "GCP project id. Required at plan and apply time."
}

variable "region" {
  type        = string
  description = "Region for Cloud Run, Artifact Registry, buckets, and Model Armor."
  default     = "us-central1"
}

variable "billing_account_id" {
  type        = string
  description = "Billing account id for the budget alert. Empty skips the budget."
  default     = ""
}

variable "alert_email" {
  type        = string
  description = "Notification email. Empty skips the alert policy and email channel."
  default     = ""
}

variable "budget_amount" {
  type        = number
  description = "Budget ceiling. Not a measurement of current spend."
  default     = 10
}

variable "budget_currency" {
  type        = string
  description = "Currency code for the budget. Must match the billing account."
  default     = "AUD"
}

variable "github_repository" {
  type        = string
  description = "GitHub owner/name for Workload Identity Federation. Empty skips the pool."
  default     = ""
}

variable "operator_members" {
  type        = list(string)
  description = "IAM members granted roles/run.invoker for manual smoke tests, for example user:you@example.com."
  default     = []
}

variable "triage_confidence_threshold" {
  type        = string
  description = "Flash triage confidence below this value is re-judged by Gemini Pro. Code still escalates Model Armor matches and bank-detail changes."
  default     = "0.8"
}

variable "bootstrap_image" {
  type        = string
  description = "Image used on the first apply. The deploy workflow replaces it."
  default     = "us-docker.pkg.dev/cloudrun/container/hello"
}
