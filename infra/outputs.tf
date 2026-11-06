# Printed after apply. The running job gets the connection name from its container env, not from this output.

output "image_repository" {
  description = "Repository prefix. Cloud Build pushes bot:latest under it."
  value       = "${var.region}-docker.pkg.dev/${var.project_id}/${google_artifact_registry_repository.bot.repository_id}/bot"
}

output "instance_connection_name" {
  description = "Cloud SQL connection name. The job receives this as INSTANCE_CONNECTION_NAME."
  value       = google_sql_database_instance.main.connection_name
}
