variable "project_id" {
  type        = string
  description = "GCP project id."
}

variable "github_repository" {
  type        = string
  description = "GitHub repository as owner/name. Empty skips the Workload Identity pool."
  default     = ""
}
