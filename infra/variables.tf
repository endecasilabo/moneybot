# Inputs. An empty image is how `infra` applies without creating the jobs.

variable "deployer_account_id" {
  type        = string
  default     = "moneybot-sa"
  description = "Existing GitHub Actions service account. Terraform does not create it."
}

variable "image" {
  type        = string
  default     = ""
  description = "bot image URI with tag. Empty skips the Cloud Run jobs and the schedulers, so infra can apply before the first image exists."
}

variable "project_id" {
  type        = string
  description = "Existing GCP project. Terraform does not create it."
}

variable "region" {
  type        = string
  default     = "us-central1"
  description = "Region for Cloud Run, BigQuery, Artifact Registry, and Cloud Scheduler. Scheduler must be available here."
}

variable "bars_cron" {
  type        = string
  default     = "35 10-16 * * 1-5"
  description = "America/New_York. Minute 35, 10:00-16:59, weekdays. Stores 1Hour SIP bars. A later run starts after the last stored bar."
}

variable "snapshot_cron" {
  type        = string
  default     = "*/15 9-16 * * 1-5"
  description = "America/New_York. Every 15 minutes, 09:00-16:59, weekdays. Read-only account snapshot."
}
