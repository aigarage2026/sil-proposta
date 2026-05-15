locals {
  ar_repo  = "sil-proposta"
  image    = "${var.region}-docker.pkg.dev/${var.project_id}/${local.ar_repo}/${var.service_name}:${var.image_tag}"
  sa_email = google_service_account.run_sa.email

  common_labels = {
    product     = "sil-proposta"
    environment = var.environment
    managed_by  = "terraform"
  }
}

# ── Artifact Registry ──────────────────────────────────────────────────────

resource "google_artifact_registry_repository" "sil_proposta" {
  location      = var.region
  repository_id = local.ar_repo
  format        = "DOCKER"
  description   = "Sil-Proposta backend container images."
  labels        = local.common_labels
}

# ── Runtime service account ───────────────────────────────────────────────

resource "google_service_account" "run_sa" {
  account_id   = "${var.service_name}-run"
  display_name = "Cloud Run SA — ${var.service_name}"
}

# Allow the SA to read each secret used by the service.
resource "google_secret_manager_secret_iam_member" "database_url" {
  secret_id = var.secret_database_url
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${local.sa_email}"
}

resource "google_secret_manager_secret_iam_member" "jwt_secret" {
  secret_id = var.secret_jwt_secret
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${local.sa_email}"
}

resource "google_secret_manager_secret_iam_member" "portal_hmac" {
  secret_id = var.secret_portal_hmac
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${local.sa_email}"
}

resource "google_secret_manager_secret_iam_member" "openai" {
  count     = var.enable_optional_secrets ? 1 : 0
  secret_id = var.secret_openai
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${local.sa_email}"
}

resource "google_secret_manager_secret_iam_member" "anthropic" {
  count     = var.enable_optional_secrets ? 1 : 0
  secret_id = var.secret_anthropic
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${local.sa_email}"
}

resource "google_secret_manager_secret_iam_member" "sentry" {
  count     = var.enable_optional_secrets ? 1 : 0
  secret_id = var.secret_sentry_dsn
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${local.sa_email}"
}

# ── Cloud Run service ─────────────────────────────────────────────────────

resource "google_cloud_run_v2_service" "sil_proposta" {
  name     = var.service_name
  location = var.region
  ingress  = "INGRESS_TRAFFIC_ALL"
  labels   = local.common_labels

  template {
    service_account = local.sa_email

    scaling {
      min_instance_count = var.min_instances
      max_instance_count = var.max_instances
    }

    containers {
      image = local.image

      ports {
        container_port = 8080
      }

      resources {
        limits = {
          cpu    = var.cpu
          memory = var.memory
        }
        cpu_idle = true
      }

      # ── plain env ───────────────────────────────────────────────
      env {
        name  = "SENTRY_ENVIRONMENT"
        value = var.environment
      }
      env {
        name  = "DEBUG"
        value = var.environment == "prd" ? "false" : "true"
      }
      env {
        name  = "JWT_STRICT_VALIDATION"
        value = var.environment == "prd" ? "true" : "false"
      }
      env {
        name  = "EVENT_CONSUMER_ENABLED"
        value = "true"
      }

      # ── secret env ──────────────────────────────────────────────
      env {
        name = "DATABASE_URL"
        value_source {
          secret_key_ref {
            secret  = var.secret_database_url
            version = "latest"
          }
        }
      }
      env {
        name = "JWT_SECRET"
        value_source {
          secret_key_ref {
            secret  = var.secret_jwt_secret
            version = "latest"
          }
        }
      }
      env {
        name = "PORTAL_HMAC_SECRET"
        value_source {
          secret_key_ref {
            secret  = var.secret_portal_hmac
            version = "latest"
          }
        }
      }

      dynamic "env" {
        for_each = var.enable_optional_secrets ? [1] : []
        content {
          name = "OPENAI_API_KEY"
          value_source {
            secret_key_ref {
              secret  = var.secret_openai
              version = "latest"
            }
          }
        }
      }
      dynamic "env" {
        for_each = var.enable_optional_secrets ? [1] : []
        content {
          name = "ANTHROPIC_API_KEY"
          value_source {
            secret_key_ref {
              secret  = var.secret_anthropic
              version = "latest"
            }
          }
        }
      }
      dynamic "env" {
        for_each = var.enable_optional_secrets ? [1] : []
        content {
          name = "SENTRY_DSN"
          value_source {
            secret_key_ref {
              secret  = var.secret_sentry_dsn
              version = "latest"
            }
          }
        }
      }

      startup_probe {
        http_get { path = "/health" }
        initial_delay_seconds = 5
        period_seconds        = 5
        failure_threshold     = 6
        timeout_seconds       = 3
      }

      liveness_probe {
        http_get { path = "/health" }
        period_seconds    = 30
        failure_threshold = 3
        timeout_seconds   = 3
      }
    }
  }

  depends_on = [
    google_artifact_registry_repository.sil_proposta,
    google_secret_manager_secret_iam_member.database_url,
    google_secret_manager_secret_iam_member.jwt_secret,
    google_secret_manager_secret_iam_member.portal_hmac,
  ]
}

# Public invoker (Cloudflare tunnel sits in front in prod; we still allow
# the Cloud Run URL to be reachable so health checks + diag work).
resource "google_cloud_run_v2_service_iam_member" "public" {
  name     = google_cloud_run_v2_service.sil_proposta.name
  location = google_cloud_run_v2_service.sil_proposta.location
  role     = "roles/run.invoker"
  member   = "allUsers"
}
