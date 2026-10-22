resource "google_service_account" "this" {
  project      = var.project_id
  account_id   = var.service_account_id
  display_name = "LedgerGuard ${var.name}"
}

resource "google_cloud_run_v2_service" "this" {
  project             = var.project_id
  name                = var.name
  location            = var.region
  ingress             = var.ingress
  deletion_protection = false

  template {
    service_account                  = google_service_account.this.email
    timeout                          = "300s"
    max_instance_request_concurrency = 4

    scaling {
      min_instance_count = 0
      max_instance_count = var.max_instances
    }

    containers {
      image = var.image

      ports {
        container_port = 8080
      }

      resources {
        limits = {
          cpu    = "1"
          memory = "512Mi"
        }
        cpu_idle = true
      }

      dynamic "env" {
        for_each = var.env
        content {
          name  = env.key
          value = env.value
        }
      }
    }
  }

  traffic {
    type    = "TRAFFIC_TARGET_ALLOCATION_TYPE_LATEST"
    percent = 100
  }

  # Image and traffic are applied by the deploy workflow (tagged revision, no traffic, then shift).
  # Env is ignored after create so a later apply does not wipe AGENT_URL set by that workflow.
  lifecycle {
    ignore_changes = [
      template[0].containers[0].image,
      template[0].containers[0].env,
      traffic,
      client,
      client_version,
    ]
  }
}

resource "google_cloud_run_v2_service_iam_member" "invoker" {
  for_each = toset(var.invokers)
  project  = var.project_id
  location = google_cloud_run_v2_service.this.location
  name     = google_cloud_run_v2_service.this.name
  role     = "roles/run.invoker"
  member   = each.value
}
