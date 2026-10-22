resource "google_logging_metric" "armor_matches" {
  project = var.project_id
  name    = "ledgerguard_model_armor_matches"
  filter  = "resource.type=\"modelarmor.googleapis.com/Template\" AND jsonPayload.filterMatchState=\"MATCH_FOUND\""

  metric_descriptor {
    metric_kind = "DELTA"
    value_type  = "INT64"
    unit        = "1"
  }
}

resource "google_logging_metric" "armor_failures" {
  project = var.project_id
  name    = "ledgerguard_model_armor_failures"
  # Field path should be confirmed against a real sanitize log. A wrong path stays at zero.
  filter = "resource.type=\"modelarmor.googleapis.com/Template\" AND (jsonPayload.invocationResult=\"PARTIAL\" OR jsonPayload.invocationResult=\"FAILURE\")"

  metric_descriptor {
    metric_kind = "DELTA"
    value_type  = "INT64"
    unit        = "1"
  }
}

resource "google_monitoring_notification_channel" "email" {
  count        = var.alert_email == "" ? 0 : 1
  project      = var.project_id
  display_name = "LedgerGuard email"
  type         = "email"
  labels = {
    email_address = var.alert_email
  }
}

resource "google_monitoring_alert_policy" "armor_burst" {
  count        = var.alert_email == "" ? 0 : 1
  project      = var.project_id
  display_name = "LedgerGuard Model Armor match burst"
  combiner     = "OR"
  enabled      = true

  conditions {
    display_name = "More than 20 MATCH_FOUND events in 5 minutes"
    condition_threshold {
      filter          = "metric.type=\"logging.googleapis.com/user/${google_logging_metric.armor_matches.name}\" AND resource.type=\"global\""
      duration        = "0s"
      comparison      = "COMPARISON_GT"
      threshold_value = 20
      aggregations {
        alignment_period   = "300s"
        per_series_aligner = "ALIGN_SUM"
      }
    }
  }

  notification_channels = [google_monitoring_notification_channel.email[0].id]

  alert_strategy {
    auto_close = "1800s"
  }
}

resource "google_billing_budget" "ledgerguard" {
  count           = var.billing_account_id == "" ? 0 : 1
  billing_account = var.billing_account_id
  display_name    = "ledgerguard"

  budget_filter {
    projects = ["projects/${var.project_number}"]
  }

  amount {
    specified_amount {
      currency_code = var.budget_currency
      units         = tostring(var.budget_amount)
    }
  }

  threshold_rules {
    threshold_percent = 0.5
  }
  threshold_rules {
    threshold_percent = 0.9
  }
  threshold_rules {
    threshold_percent = 1.0
  }

  dynamic "all_updates_rule" {
    for_each = var.alert_email == "" ? [] : [1]
    content {
      monitoring_notification_channels = [google_monitoring_notification_channel.email[0].id]
      disable_default_iam_recipients   = false
    }
  }
}
