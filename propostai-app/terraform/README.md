# Terraform — PropostAI Cloud Run

Skeleton infrastructure for deploying `propostai-app/backend` to GCP
Cloud Run. Aligned with v3 §16.7 platform defaults:

- Cloud Run + Cloud SQL Postgres (shared cluster, DB-per-product)
- GCP Artifact Registry for container images
- GCP Secret Manager for secrets
- VPC Connector for private DB access

## What's here

- `providers.tf` — Google + Google-beta providers, terraform >= 1.5
- `variables.tf` — `project_id`, `region`, `service_name`, `image_tag`,
  `environment` (dev | prd) and the secret names this service needs
- `main.tf` — Artifact Registry repo + Cloud Run service. Reads secrets
  from Secret Manager (existing) and mounts them as env vars. Service
  account binding kept minimal: read secrets + connect to Cloud SQL.
- `outputs.tf` — Cloud Run URL, service account email.

## Bootstrap (one-time)

Before `terraform apply`, create these out-of-band:

1. **Project** with billing enabled.
2. **Secrets in Secret Manager** (names match `variables.tf`):
   - `propostai-database-url`
   - `propostai-jwt-secret`
   - `propostai-portal-hmac-secret`
   - `propostai-openai-api-key` (optional — keep blank if demo-only)
   - `propostai-anthropic-api-key` (optional)
3. **Terraform state bucket**: `gs://${project_id}-terraform-state`.

## Typical flow

```
cd propostai-app/terraform
terraform init -backend-config="bucket=<project_id>-terraform-state"
terraform plan  -var="project_id=..." -var="image_tag=v1.0.0"
terraform apply -var="project_id=..." -var="image_tag=v1.0.0"
```

The image with that tag must already exist in Artifact Registry. The
`.github/workflows/deploy.yml` workflow builds + pushes then runs
`gcloud run deploy` directly (skipping terraform for the per-commit deploy)
— terraform is only used for the infra skeleton + upgrades to it.

## Not provisioned here (deferred until needed)

- Cloud SQL instance + database — currently expected to exist; create
  via the platform's shared Terraform module when ready.
- VPC Connector — needed for private Cloud SQL; out of scope for the
  initial deploy.
- Cloudflare tunnel + DNS — managed at the platform level (v3 §16.7).
- Sentry project, Qdrant cluster — created via their providers, not GCP.
