variable "project_id" {
  type        = string
  description = "GCP project id."
}

variable "region" {
  type        = string
  description = "Model Armor location. us-central1 for the scaffold. See docs/adr/0001."
  default     = "us-central1"
}

variable "inspect_template" {
  type        = string
  description = "Full DLP inspect template resource name for the response template."
}

variable "deidentify_template" {
  type        = string
  description = "Full DLP de-identify template resource name for the response template."
}
