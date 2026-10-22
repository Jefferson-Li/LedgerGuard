locals {
  enabled = var.github_repository != ""
  deployer_roles = [
    "roles/run.admin",
    "roles/artifactregistry.writer",
    "roles/resourcemanager.projectIamAdmin",
    "roles/serviceusage.serviceUsageAdmin",
    "roles/storage.admin",
    "roles/secretmanager.admin",
    "roles/logging.configWriter",
    "roles/monitoring.editor",
    "roles/dlp.admin",
    "roles/modelarmor.admin",
    "roles/datastore.user",
  ]
}

resource "google_service_account" "deployer" {
  project      = var.project_id
  account_id   = "ledgerguard-deployer"
  display_name = "LedgerGuard GitHub deployer"
}

resource "google_project_iam_member" "deployer_sa_admin" {
  #checkov:skip=CKV_GCP_49:Terraform apply creates the runtime service accounts, so the deployer keeps serviceAccountAdmin
  project = var.project_id
  role    = "roles/iam.serviceAccountAdmin"
  member  = "serviceAccount:${google_service_account.deployer.email}"
}

resource "google_project_iam_member" "deployer" {
  for_each = toset(local.deployer_roles)
  project  = var.project_id
  role     = each.value
  member   = "serviceAccount:${google_service_account.deployer.email}"
}

resource "google_iam_workload_identity_pool" "github" {
  count                     = local.enabled ? 1 : 0
  project                   = var.project_id
  workload_identity_pool_id = "ledgerguard-github"
  display_name              = "LedgerGuard GitHub"
  description               = "Keyless GitHub Actions deploys for LedgerGuard."
}

resource "google_iam_workload_identity_pool_provider" "github" {
  #checkov:skip=CKV_GCP_125:Condition pins assertion.repository to one repo. Checkov only accepts a literal assertion.sub repo claim, which cannot be a variable.
  count                              = local.enabled ? 1 : 0
  project                            = var.project_id
  workload_identity_pool_id          = google_iam_workload_identity_pool.github[0].workload_identity_pool_id
  workload_identity_pool_provider_id = "github"
  display_name                       = "GitHub OIDC"
  attribute_mapping = {
    "google.subject"       = "assertion.sub"
    "attribute.repository" = "assertion.repository"
  }
  attribute_condition = "assertion.repository == \"${var.github_repository}\""
  oidc {
    issuer_uri = "https://token.actions.githubusercontent.com"
  }
}

resource "google_service_account_iam_member" "wif" {
  count              = local.enabled ? 1 : 0
  service_account_id = google_service_account.deployer.name
  role               = "roles/iam.workloadIdentityUser"
  member             = "principalSet://iam.googleapis.com/${google_iam_workload_identity_pool.github[0].name}/attribute.repository/${var.github_repository}"
}
