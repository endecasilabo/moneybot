# Inputs. An empty image is how `infra` applies without creating the jobs.

variable "db_tier" {
  type        = string
  default     = "db-f1-micro"
  description = "Cloud SQL machine size. This tier stays on; it does not scale to zero."
}

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
  description = "Region for Cloud Run, Cloud SQL, Artifact Registry, and Cloud Scheduler. Scheduler must be available here."
}

variable "snapshot_cron" {
  type        = string
  default     = "*/15 9-16 * * 1-5"
  description = "America/New_York. Every 15 minutes, 09:00-16:59, weekdays. Read-only account snapshot."
}

variable "trade_cron" {
  type        = string
  default     = "*/5 12-16 * * 1-5"
  description = "America/New_York. Every 5 minutes, 12:00-16:59, weekdays. The process itself only submits 10-20 minutes before the close."
}
