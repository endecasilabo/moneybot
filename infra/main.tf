terraform {
  required_version = ">= 1.5"
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 6.0"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.6"
    }
  }
}

provider "google" {
  project = var.project_id
  region  = var.region
}

variable "project_id" {
  type = string
}

variable "region" {
  type    = string
  default = "us-central1"
}

variable "image" {
  type        = string
  default     = ""
  description = "Image URI with tag. Empty skips the Cloud Run jobs and the schedulers."
}

variable "trade_cron" {
  type    = string
  default = "*/5 12-16 * * 1-5"
}

variable "snapshot_cron" {
  type    = string
  default = "*/15 9-16 * * 1-5"
}

variable "db_tier" {
  type    = string
  default = "db-f1-micro"
}

variable "github_repository" {
  type        = string
  default     = ""
  description = "GitHub repo owner/name. Empty skips the Actions identity pool."
}

data "google_project" "this" {}

locals {
  jobs = {
    trade = {
      args = ["trade"]
      cron = var.trade_cron
    }
    snapshot = {
      args = ["snapshot"]
      cron = var.snapshot_cron
    }
  }
  active_jobs = { for name, job in local.jobs : name => job if var.image != "" }
}

resource "google_project_service" "apis" {
  for_each = toset([
    "run.googleapis.com",
    "sqladmin.googleapis.com",
    "cloudscheduler.googleapis.com",
    "secretmanager.googleapis.com",
    "artifactregistry.googleapis.com",
    "cloudbuild.googleapis.com",
    "iam.googleapis.com",
  ])
  service            = each.value
  disable_on_destroy = false
}

resource "google_artifact_registry_repository" "bot" {
  location      = var.region
  repository_id = "moneybot"
  format        = "DOCKER"
  depends_on    = [google_project_service.apis]
}

resource "random_password" "db" {
  length  = 32
  special = false
}

resource "google_secret_manager_secret" "db_password" {
  secret_id = "moneybot-db-password"
  replication {
    auto {}
  }
  depends_on = [google_project_service.apis]
}

resource "google_secret_manager_secret_version" "db_password" {
  secret      = google_secret_manager_secret.db_password.id
  secret_data = random_password.db.result
}

resource "google_secret_manager_secret" "alpaca_key" {
  secret_id = "moneybot-alpaca-key"
  replication {
    auto {}
  }
  depends_on = [google_project_service.apis]
}

resource "google_secret_manager_secret" "alpaca_secret" {
  secret_id = "moneybot-alpaca-secret"
  replication {
    auto {}
  }
  depends_on = [google_project_service.apis]
}

resource "google_sql_database_instance" "main" {
  name                = "moneybot"
  database_version    = "POSTGRES_16"
  region              = var.region
  deletion_protection = true

  settings {
    tier                        = var.db_tier
    edition                     = "ENTERPRISE"
    deletion_protection_enabled = true
    ip_configuration {
      ipv4_enabled = true
    }
  }

  depends_on = [google_project_service.apis]
}

resource "google_sql_database" "bot" {
  name     = "moneybot"
  instance = google_sql_database_instance.main.name
}

resource "google_sql_user" "bot" {
  name     = "moneybot"
  instance = google_sql_database_instance.main.name
  password = random_password.db.result
}

resource "google_service_account" "job" {
  account_id   = "moneybot-job"
  display_name = "moneybot Cloud Run job"
}

resource "google_service_account" "scheduler" {
  account_id   = "moneybot-scheduler"
  display_name = "moneybot Cloud Scheduler"
}

resource "google_project_iam_member" "job_sql" {
  project = var.project_id
  role    = "roles/cloudsql.client"
  member  = "serviceAccount:${google_service_account.job.email}"
}

resource "google_secret_manager_secret_iam_member" "job_db" {
  secret_id = google_secret_manager_secret.db_password.id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.job.email}"
}

resource "google_secret_manager_secret_iam_member" "job_alpaca_key" {
  secret_id = google_secret_manager_secret.alpaca_key.id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.job.email}"
}

resource "google_secret_manager_secret_iam_member" "job_alpaca_secret" {
  secret_id = google_secret_manager_secret.alpaca_secret.id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.job.email}"
}

resource "google_artifact_registry_repository_iam_member" "job_reader" {
  location   = google_artifact_registry_repository.bot.location
  repository = google_artifact_registry_repository.bot.repository_id
  role       = "roles/artifactregistry.reader"
  member     = "serviceAccount:${google_service_account.job.email}"
}

resource "google_service_account_iam_member" "scheduler_token_creator" {
  service_account_id = google_service_account.scheduler.name
  role               = "roles/iam.serviceAccountTokenCreator"
  member             = "serviceAccount:service-${data.google_project.this.number}@gcp-sa-cloudscheduler.iam.gserviceaccount.com"
  depends_on         = [google_project_service.apis]
}

resource "google_cloud_run_v2_job" "bot" {
  for_each = local.active_jobs
  name     = "moneybot-${each.key}"
  location = var.region

  template {
    template {
      service_account = google_service_account.job.email
      timeout         = "300s"
      max_retries     = 0

      containers {
        image   = var.image
        command = ["python", "-m", "moneybot"]
        args    = each.value.args

        env {
          name  = "BOT_CONFIG"
          value = "/app/config/bot.yaml"
        }
        env {
          name  = "SCHEMA_PATH"
          value = "/app/schema.sql"
        }
        env {
          name  = "INSTANCE_CONNECTION_NAME"
          value = google_sql_database_instance.main.connection_name
        }
        env {
          name  = "DB_NAME"
          value = google_sql_database.bot.name
        }
        env {
          name  = "DB_USER"
          value = google_sql_user.bot.name
        }
        env {
          name = "DB_PASSWORD"
          value_source {
            secret_key_ref {
              secret  = google_secret_manager_secret.db_password.secret_id
              version = "latest"
            }
          }
        }
        env {
          name = "ALPACA_KEY"
          value_source {
            secret_key_ref {
              secret  = google_secret_manager_secret.alpaca_key.secret_id
              version = "latest"
            }
          }
        }
        env {
          name = "ALPACA_SECRET"
          value_source {
            secret_key_ref {
              secret  = google_secret_manager_secret.alpaca_secret.secret_id
              version = "latest"
            }
          }
        }

        volume_mounts {
          name       = "cloudsql"
          mount_path = "/cloudsql"
        }
      }

      volumes {
        name = "cloudsql"
        cloud_sql_instance {
          instances = [google_sql_database_instance.main.connection_name]
        }
      }
    }
  }

  depends_on = [
    google_project_service.apis,
    google_project_iam_member.job_sql,
    google_secret_manager_secret_iam_member.job_db,
    google_secret_manager_secret_iam_member.job_alpaca_key,
    google_secret_manager_secret_iam_member.job_alpaca_secret,
    google_artifact_registry_repository_iam_member.job_reader,
    google_secret_manager_secret_version.db_password,
  ]
}

resource "google_cloud_run_v2_job_iam_member" "invoker" {
  for_each = local.active_jobs
  name     = google_cloud_run_v2_job.bot[each.key].name
  location = var.region
  role     = "roles/run.invoker"
  member   = "serviceAccount:${google_service_account.scheduler.email}"
}

resource "google_cloud_scheduler_job" "bot" {
  for_each    = local.active_jobs
  name        = "moneybot-${each.key}"
  region      = var.region
  schedule    = each.value.cron
  time_zone   = "America/New_York"
  description = "Run moneybot ${each.key}"

  http_target {
    http_method = "POST"
    uri         = "https://run.googleapis.com/v2/projects/${var.project_id}/locations/${var.region}/jobs/${google_cloud_run_v2_job.bot[each.key].name}:run"
    body        = base64encode("{}")
    headers = {
      "Content-Type" = "application/json"
    }
    oauth_token {
      service_account_email = google_service_account.scheduler.email
      scope                 = "https://www.googleapis.com/auth/cloud-platform"
    }
  }

  depends_on = [
    google_project_service.apis,
    google_cloud_run_v2_job_iam_member.invoker,
    google_service_account_iam_member.scheduler_token_creator,
  ]
}

locals {
  cloudbuild_sa = "${data.google_project.this.number}@cloudbuild.gserviceaccount.com"
}

resource "google_artifact_registry_repository_iam_member" "cloudbuild_writer" {
  location   = google_artifact_registry_repository.bot.location
  repository = google_artifact_registry_repository.bot.repository_id
  role       = "roles/artifactregistry.writer"
  member     = "serviceAccount:${local.cloudbuild_sa}"
  depends_on = [google_project_service.apis]
}

resource "google_project_iam_member" "cloudbuild_run" {
  project    = var.project_id
  role       = "roles/run.developer"
  member     = "serviceAccount:${local.cloudbuild_sa}"
  depends_on = [google_project_service.apis]
}

resource "google_project_iam_member" "cloudbuild_logs" {
  project    = var.project_id
  role       = "roles/logging.logWriter"
  member     = "serviceAccount:${local.cloudbuild_sa}"
  depends_on = [google_project_service.apis]
}

resource "google_service_account_iam_member" "cloudbuild_runs_as_job" {
  service_account_id = google_service_account.job.name
  role               = "roles/iam.serviceAccountUser"
  member             = "serviceAccount:${local.cloudbuild_sa}"
  depends_on         = [google_project_service.apis]
}

resource "google_service_account" "ci" {
  count        = var.github_repository == "" ? 0 : 1
  account_id   = "moneybot-ci"
  display_name = "moneybot GitHub Actions"
}

resource "google_project_iam_member" "ci_builds" {
  count   = var.github_repository == "" ? 0 : 1
  project = var.project_id
  role    = "roles/cloudbuild.builds.editor"
  member  = "serviceAccount:${google_service_account.ci[0].email}"
}

resource "google_service_account_iam_member" "ci_submits_builds" {
  count              = var.github_repository == "" ? 0 : 1
  service_account_id = "projects/${var.project_id}/serviceAccounts/${local.cloudbuild_sa}"
  role               = "roles/iam.serviceAccountUser"
  member             = "serviceAccount:${google_service_account.ci[0].email}"
  depends_on         = [google_project_service.apis]
}

resource "google_iam_workload_identity_pool" "github" {
  count                     = var.github_repository == "" ? 0 : 1
  workload_identity_pool_id = "moneybot-github"
  display_name              = "moneybot GitHub"
  depends_on                = [google_project_service.apis]
}

resource "google_iam_workload_identity_pool_provider" "github" {
  count                              = var.github_repository == "" ? 0 : 1
  workload_identity_pool_id          = google_iam_workload_identity_pool.github[0].workload_identity_pool_id
  workload_identity_pool_provider_id = "github"
  display_name                       = "GitHub"
  attribute_mapping = {
    "google.subject"       = "assertion.sub"
    "attribute.repository" = "assertion.repository"
  }
  attribute_condition = "assertion.repository=='${var.github_repository}'"
  oidc {
    issuer_uri = "https://token.actions.githubusercontent.com"
  }
}

resource "google_service_account_iam_member" "ci_wif" {
  count              = var.github_repository == "" ? 0 : 1
  service_account_id = google_service_account.ci[0].name
  role               = "roles/iam.workloadIdentityUser"
  member             = "principalSet://iam.googleapis.com/${google_iam_workload_identity_pool.github[0].name}/attribute.repository/${var.github_repository}"
}

output "image_repository" {
  value = "${var.region}-docker.pkg.dev/${var.project_id}/${google_artifact_registry_repository.bot.repository_id}/bot"
}

output "instance_connection_name" {
  value = google_sql_database_instance.main.connection_name
}

output "wif_provider" {
  value = one(google_iam_workload_identity_pool_provider.github[*].name)
}

output "ci_service_account" {
  value = one(google_service_account.ci[*].email)
}
