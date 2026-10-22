variable "project_id" {
  type        = string
  description = "GCP project id."
}

variable "region" {
  type        = string
  description = "Cloud Run region."
}

variable "name" {
  type        = string
  description = "Cloud Run service name."
}

variable "image" {
  type        = string
  description = "Bootstrap container image. CI replaces it; Terraform ignores later image changes."
}

variable "service_account_id" {
  type        = string
  description = "Account id for this service's runtime service account. Max 30 characters."
}

variable "env" {
  type        = map(string)
  description = "Plain environment variables. Changes after the first apply are ignored so deploy can set AGENT_URL."
  default     = {}
}

variable "invokers" {
  type        = list(string)
  description = "IAM members granted roles/run.invoker. Do not include allUsers."
  default     = []
}

variable "max_instances" {
  type        = number
  description = "Cloud Run max instances. Scale to zero is always allowed."
  default     = 2
}

variable "ingress" {
  type        = string
  description = "Cloud Run ingress. IAM still requires roles/run.invoker; there is no allUsers binding."
  default     = "INGRESS_TRAFFIC_ALL"
}
