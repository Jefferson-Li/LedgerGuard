data "google_project" "this" {
  project_id = var.project_id
}

locals {
  apis = toset([
    "run.googleapis.com",
    "artifactregistry.googleapis.com",
    "aiplatform.googleapis.com",
    "modelarmor.googleapis.com",
    "secretmanager.googleapis.com",
    "dlp.googleapis.com",
    "storage.googleapis.com",
    "firestore.googleapis.com",
    "iam.googleapis.com",
    "iamcredentials.googleapis.com",
    "cloudtrace.googleapis.com",
    "logging.googleapis.com",
    "monitoring.googleapis.com",
    "cloudbuild.googleapis.com",
    "billingbudgets.googleapis.com",
  ])
  common_env = {
    GOOGLE_CLOUD_PROJECT        = var.project_id
    GOOGLE_CLOUD_LOCATION       = "global"
    GOOGLE_GENAI_USE_ENTERPRISE = "TRUE"
    LEDGERGUARD_MODEL           = "gemini-2.5-flash"
  }
}

resource "google_project_service" "apis" {
  for_each           = local.apis
  project            = var.project_id
  service            = each.value
  disable_on_destroy = false
}

resource "google_artifact_registry_repository" "ledgerguard" {
  #checkov:skip=CKV_GCP_84:Google-managed encryption. A customer-managed key is not required for this scaffold.
  project       = var.project_id
  location      = var.region
  repository_id = "ledgerguard"
  description   = "LedgerGuard container images"
  format        = "DOCKER"

  docker_config {
    immutable_tags = true
  }

  depends_on = [google_project_service.apis]
}

resource "google_storage_bucket" "logs" {
  #checkov:skip=CKV_GCP_62:This bucket is the access-log destination for the raw and clean buckets. Logging it to itself is circular.
  project                     = var.project_id
  name                        = "${var.project_id}-lg-logs"
  location                    = var.region
  uniform_bucket_level_access = true
  public_access_prevention    = "enforced"
  force_destroy               = true

  versioning {
    enabled = true
  }
}

resource "google_storage_bucket" "raw" {
  project                     = var.project_id
  name                        = "${var.project_id}-lg-raw"
  location                    = var.region
  uniform_bucket_level_access = true
  public_access_prevention    = "enforced"
  force_destroy               = true

  versioning {
    enabled = true
  }

  logging {
    log_bucket = google_storage_bucket.logs.name
  }

  lifecycle_rule {
    condition {
      age = 30
    }
    action {
      type = "Delete"
    }
  }
}

resource "google_storage_bucket" "clean" {
  project                     = var.project_id
  name                        = "${var.project_id}-lg-clean"
  location                    = var.region
  uniform_bucket_level_access = true
  public_access_prevention    = "enforced"
  force_destroy               = true

  versioning {
    enabled = true
  }

  logging {
    log_bucket = google_storage_bucket.logs.name
  }

  lifecycle_rule {
    condition {
      age = 30
    }
    action {
      type = "Delete"
    }
  }
}

resource "google_secret_manager_secret" "runtime_config" {
  project   = var.project_id
  secret_id = "ledgerguard-runtime-config"

  replication {
    auto {}
  }

  depends_on = [google_project_service.apis]
}

resource "google_firestore_database" "default" {
  project     = var.project_id
  name        = "(default)"
  location_id = var.region
  type        = "FIRESTORE_NATIVE"

  depends_on = [google_project_service.apis]
}

module "sdp" {
  source         = "../../modules/sdp"
  project_id     = var.project_id
  project_number = data.google_project.this.number

  depends_on = [google_project_service.apis]
}

module "armor" {
  source              = "../../modules/model_armor"
  project_id          = var.project_id
  region              = var.region
  inspect_template    = module.sdp.inspect_template
  deidentify_template = module.sdp.deidentify_template

  depends_on = [google_project_service.apis]
}

module "wif" {
  source            = "../../modules/wif"
  project_id        = var.project_id
  github_repository = var.github_repository

  depends_on = [google_project_service.apis]
}

module "monitoring" {
  source             = "../../modules/monitoring"
  project_id         = var.project_id
  project_number     = data.google_project.this.number
  billing_account_id = var.billing_account_id
  alert_email        = var.alert_email
  budget_amount      = var.budget_amount
  budget_currency    = var.budget_currency

  depends_on = [google_project_service.apis]
}

module "erp" {
  source             = "../../modules/cloud_run_service"
  project_id         = var.project_id
  region             = var.region
  name               = "erp-mcp"
  image              = var.bootstrap_image
  service_account_id = "ledgerguard-erp"
  max_instances      = 2
  invokers           = var.operator_members
  env = {
    GOOGLE_CLOUD_PROJECT = var.project_id
  }

  depends_on = [google_project_service.apis]
}

module "invoice" {
  source             = "../../modules/cloud_run_service"
  project_id         = var.project_id
  region             = var.region
  name               = "invoice-mcp"
  image              = var.bootstrap_image
  service_account_id = "ledgerguard-invoice"
  max_instances      = 2
  invokers           = var.operator_members
  env = {
    GOOGLE_CLOUD_PROJECT        = var.project_id
    MODEL_ARMOR_PROMPT_TEMPLATE = module.armor.prompt_template
  }

  depends_on = [google_project_service.apis]
}

module "matching" {
  source             = "../../modules/cloud_run_service"
  project_id         = var.project_id
  region             = var.region
  name               = "matching-agent"
  image              = var.bootstrap_image
  service_account_id = "ledgerguard-matching"
  max_instances      = 2
  invokers           = var.operator_members
  env = merge(local.common_env, {
    ERP_MCP_URL                   = "${module.erp.uri}/mcp"
    INVOICE_MCP_URL               = "${module.invoice.uri}/mcp"
    MCP_AUTH_MODE                 = "id_token"
    MODEL_ARMOR_PROMPT_TEMPLATE   = module.armor.prompt_template
    MODEL_ARMOR_RESPONSE_TEMPLATE = module.armor.response_template
  })

  depends_on = [google_project_service.apis]
}

module "orchestrator" {
  source             = "../../modules/cloud_run_service"
  project_id         = var.project_id
  region             = var.region
  name               = "ap-orchestrator"
  image              = var.bootstrap_image
  service_account_id = "ledgerguard-orch"
  max_instances      = 2
  invokers           = var.operator_members
  env = merge(local.common_env, {
    MATCHING_AGENT_URL            = module.matching.uri
    A2A_AUTH_MODE                 = "id_token"
    MODEL_ARMOR_PROMPT_TEMPLATE   = module.armor.prompt_template
    MODEL_ARMOR_RESPONSE_TEMPLATE = module.armor.response_template
  })

  depends_on = [google_project_service.apis]
}

resource "google_cloud_run_v2_service_iam_member" "matching_calls_erp" {
  project  = var.project_id
  location = var.region
  name     = module.erp.name
  role     = "roles/run.invoker"
  member   = "serviceAccount:${module.matching.service_account_email}"
}

resource "google_cloud_run_v2_service_iam_member" "matching_calls_invoice" {
  project  = var.project_id
  location = var.region
  name     = module.invoice.name
  role     = "roles/run.invoker"
  member   = "serviceAccount:${module.matching.service_account_email}"
}

resource "google_service_account_iam_member" "deployer_acts_as_runtime" {
  for_each = {
    erp      = module.erp.service_account_email
    invoice  = module.invoice.service_account_email
    matching = module.matching.service_account_email
    orch     = module.orchestrator.service_account_email
    sdp      = google_service_account.sdp_runner.email
  }
  service_account_id = "projects/${var.project_id}/serviceAccounts/${each.value}"
  role               = "roles/iam.serviceAccountUser"
  member             = "serviceAccount:${module.wif.deployer_email}"
}

resource "google_cloud_run_v2_service_iam_member" "orchestrator_calls_matching" {
  project  = var.project_id
  location = var.region
  name     = module.matching.name
  role     = "roles/run.invoker"
  member   = "serviceAccount:${module.orchestrator.service_account_email}"
}

resource "google_project_iam_member" "erp_firestore" {
  project = var.project_id
  role    = "roles/datastore.user"
  member  = "serviceAccount:${module.erp.service_account_email}"
}

resource "google_project_iam_member" "invoice_armor" {
  project = var.project_id
  role    = "roles/modelarmor.user"
  member  = "serviceAccount:${module.invoice.service_account_email}"
}

resource "google_project_iam_member" "matching_armor" {
  project = var.project_id
  role    = "roles/modelarmor.user"
  member  = "serviceAccount:${module.matching.service_account_email}"
}

resource "google_project_iam_member" "orchestrator_armor" {
  project = var.project_id
  role    = "roles/modelarmor.user"
  member  = "serviceAccount:${module.orchestrator.service_account_email}"
}

resource "google_project_iam_member" "matching_aiplatform" {
  project = var.project_id
  role    = "roles/aiplatform.user"
  member  = "serviceAccount:${module.matching.service_account_email}"
}

resource "google_project_iam_member" "orchestrator_aiplatform" {
  project = var.project_id
  role    = "roles/aiplatform.user"
  member  = "serviceAccount:${module.orchestrator.service_account_email}"
}

resource "google_storage_bucket_iam_member" "invoice_reads_clean" {
  bucket = google_storage_bucket.clean.name
  role   = "roles/storage.objectViewer"
  member = "serviceAccount:${module.invoice.service_account_email}"
}

resource "google_service_account" "sdp_runner" {
  project      = var.project_id
  account_id   = "ledgerguard-sdp"
  display_name = "LedgerGuard SDP runner (job not implemented)"
}

resource "google_storage_bucket_iam_member" "sdp_reads_raw" {
  bucket = google_storage_bucket.raw.name
  role   = "roles/storage.objectViewer"
  member = "serviceAccount:${google_service_account.sdp_runner.email}"
}

resource "google_storage_bucket_iam_member" "sdp_writes_clean" {
  bucket = google_storage_bucket.clean.name
  role   = "roles/storage.objectAdmin"
  member = "serviceAccount:${google_service_account.sdp_runner.email}"
}

resource "google_project_iam_member" "sdp_dlp" {
  project = var.project_id
  role    = "roles/dlp.user"
  member  = "serviceAccount:${google_service_account.sdp_runner.email}"
}
