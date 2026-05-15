output "service_url" {
  description = "Public Cloud Run URL of the deployed service."
  value       = google_cloud_run_v2_service.sil_proposta.uri
}

output "service_account_email" {
  description = "Runtime service account; grant this access to Cloud SQL / GCS if needed."
  value       = google_service_account.run_sa.email
}

output "artifact_registry_repo" {
  description = "Fully qualified Artifact Registry path for builds."
  value       = "${var.region}-docker.pkg.dev/${var.project_id}/${google_artifact_registry_repository.sil_proposta.repository_id}"
}
