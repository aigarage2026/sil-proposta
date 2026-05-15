variable "project_id" {
  description = "GCP project ID hosting the Cloud Run service."
  type        = string
}

variable "region" {
  description = "GCP region for Artifact Registry + Cloud Run."
  type        = string
  default     = "southamerica-east1"
}

variable "service_name" {
  description = "Cloud Run service name."
  type        = string
  default     = "propostai"
}

variable "image_tag" {
  description = "Tag of the image in Artifact Registry to deploy."
  type        = string
}

variable "environment" {
  description = "Environment slug — appears as a Sentry tag and a Cloud Run label."
  type        = string
  default     = "dev"
  validation {
    condition     = contains(["dev", "stg", "prd"], var.environment)
    error_message = "environment must be one of: dev, stg, prd."
  }
}

variable "cpu" {
  description = "CPU per Cloud Run instance."
  type        = string
  default     = "1"
}

variable "memory" {
  description = "Memory per Cloud Run instance."
  type        = string
  default     = "1Gi"
}

variable "min_instances" {
  description = "Minimum warm instances. 0 saves cost; 1 avoids cold starts."
  type        = number
  default     = 0
}

variable "max_instances" {
  description = "Cap on concurrent instances."
  type        = number
  default     = 5
}

# ── secrets ────────────────────────────────────────────────────────────────
# Secret resources are managed out-of-band; this module only references
# them by name + mounts as env vars.

variable "secret_database_url" {
  description = "Secret Manager name for DATABASE_URL."
  type        = string
  default     = "propostai-database-url"
}

variable "secret_jwt_secret" {
  description = "Secret Manager name for JWT_SECRET."
  type        = string
  default     = "propostai-jwt-secret"
}

variable "secret_portal_hmac" {
  description = "Secret Manager name for PORTAL_HMAC_SECRET."
  type        = string
  default     = "propostai-portal-hmac-secret"
}

variable "secret_openai" {
  description = "Secret Manager name for OPENAI_API_KEY (optional)."
  type        = string
  default     = "propostai-openai-api-key"
}

variable "secret_anthropic" {
  description = "Secret Manager name for ANTHROPIC_API_KEY (optional)."
  type        = string
  default     = "propostai-anthropic-api-key"
}

variable "secret_sentry_dsn" {
  description = "Secret Manager name for SENTRY_DSN (optional)."
  type        = string
  default     = "propostai-sentry-dsn"
}

variable "enable_optional_secrets" {
  description = "Bind OPENAI/ANTHROPIC/SENTRY secrets too. Disable in envs where they don't exist yet."
  type        = bool
  default     = false
}
