# Printed after apply. The running job gets GCP_PROJECT, BQ_DATASET, and BQ_LOCATION from its container env.

output "image_repository" {
  description = "Artifact Registry repository. Cloud Build pushes {service} and {service}-bedrock under it."
  value       = "${var.region}-docker.pkg.dev/${var.project_id}/${google_artifact_registry_repository.bot.repository_id}"
}

output "dataset_id" {
  description = "BigQuery dataset id. The job receives this as BQ_DATASET."
  value       = google_bigquery_dataset.bot.dataset_id
}

output "bigquery_dataset" {
  description = "Dataset the jobs write to, as project.dataset."
  value       = "${var.project_id}.${google_bigquery_dataset.bot.dataset_id}"
}
