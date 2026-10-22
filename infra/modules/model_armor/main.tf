locals {
  rai_filters = ["HATE_SPEECH", "HARASSMENT", "SEXUALLY_EXPLICIT", "DANGEROUS"]
}

resource "google_model_armor_template" "prompt" {
  project     = var.project_id
  location    = var.region
  template_id = "ledgerguard-prompt"

  filter_config {
    rai_settings {
      dynamic "rai_filters" {
        for_each = local.rai_filters
        content {
          filter_type      = rai_filters.value
          confidence_level = "MEDIUM_AND_ABOVE"
        }
      }
    }
    pi_and_jailbreak_filter_settings {
      filter_enforcement = "ENABLED"
      confidence_level   = "HIGH"
    }
    malicious_uri_filter_settings {
      filter_enforcement = "ENABLED"
    }
  }

  template_metadata {
    log_sanitize_operations = true
    log_template_operations = true
    multi_language_detection {
      enable_multi_language_detection = true
    }
  }
}

resource "google_model_armor_template" "response" {
  project     = var.project_id
  location    = var.region
  template_id = "ledgerguard-response"

  filter_config {
    rai_settings {
      dynamic "rai_filters" {
        for_each = local.rai_filters
        content {
          filter_type      = rai_filters.value
          confidence_level = "MEDIUM_AND_ABOVE"
        }
      }
    }
    pi_and_jailbreak_filter_settings {
      filter_enforcement = "ENABLED"
      confidence_level   = "HIGH"
    }
    malicious_uri_filter_settings {
      filter_enforcement = "ENABLED"
    }
    sdp_settings {
      advanced_config {
        inspect_template    = var.inspect_template
        deidentify_template = var.deidentify_template
      }
    }
  }

  template_metadata {
    log_sanitize_operations = true
    log_template_operations = true
    multi_language_detection {
      enable_multi_language_detection = true
    }
  }
}
