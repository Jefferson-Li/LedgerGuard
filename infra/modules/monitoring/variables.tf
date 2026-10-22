variable "project_id" {
  type        = string
  description = "GCP project id."
}

variable "project_number" {
  type        = string
  description = "GCP project number for the billing budget filter."
}

variable "billing_account_id" {
  type        = string
  description = "Billing account id. Empty skips the budget resource."
  default     = ""
}

variable "alert_email" {
  type        = string
  description = "Email for Model Armor and budget notifications. Empty skips the channel and alert policy."
  default     = ""
}

variable "budget_amount" {
  type        = number
  description = "Budget amount in budget_currency. This is a ceiling alert, not a measured spend."
  default     = 10
}

variable "budget_currency" {
  type        = string
  description = "ISO currency code. Must match the billing account."
  default     = "AUD"
}
