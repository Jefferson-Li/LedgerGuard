resource "google_data_loss_prevention_inspect_template" "invoices" {
  parent       = "projects/${var.project_id}"
  display_name = "ledgerguard-inspect"
  description  = "Inspect template for LedgerGuard response screening. Invoice-number over-redaction is a known limit; a custom exclusion is not configured yet."

  inspect_config {
    info_types { name = "CREDIT_CARD_NUMBER" }
    info_types { name = "EMAIL_ADDRESS" }
    info_types { name = "PHONE_NUMBER" }
    info_types { name = "STREET_ADDRESS" }
    info_types { name = "IBAN_CODE" }
    info_types { name = "FINANCIAL_ACCOUNT_NUMBER" }
    info_types { name = "AUSTRALIA_TAX_FILE_NUMBER" }
    min_likelihood = "POSSIBLE"
    include_quote  = false
  }
}

resource "google_data_loss_prevention_deidentify_template" "invoices" {
  parent       = "projects/${var.project_id}"
  display_name = "ledgerguard-deidentify"
  description  = "Mask sensitive tokens in model responses. The batch raw-to-clean bucket job is not implemented."

  deidentify_config {
    info_type_transformations {
      transformations {
        primitive_transformation {
          character_mask_config {
            masking_character = "#"
          }
        }
      }
    }
  }
}

resource "google_project_iam_member" "modelarmor_dlp_user" {
  project = var.project_id
  role    = "roles/dlp.user"
  member  = "serviceAccount:service-${var.project_number}@gcp-sa-modelarmor.iam.gserviceaccount.com"
}

resource "google_project_iam_member" "modelarmor_dlp_reader" {
  project = var.project_id
  role    = "roles/dlp.reader"
  member  = "serviceAccount:service-${var.project_number}@gcp-sa-modelarmor.iam.gserviceaccount.com"
}
