# Printed after apply. The running job gets BQ_DATASET from its container env, not from this output.

output "image_repository" {
  description = "Repository prefix. Cloud Build pushes bot:latest under it."
  value       = "${var.region}-docker.pkg.dev/${var.project_id}/${google_artifact_registry_repository.bot.repository_id}/bot"
}

output "instance_connection_name" {
  description = "Cloud SQL connection name. Unused by the jobs since the BigQuery migration; removed with Cloud SQL."
  value       = google_sql_database_instance.main.connection_name
}

output "bigquery_dataset" {
  description = "Dataset the jobs write to. The job receives this as BQ_DATASET."
  value       = "${var.project_id}.${google_bigquery_dataset.bot.dataset_id}"
}
