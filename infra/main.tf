# Two applies, same config:
#   infra — registry, Cloud SQL, empty Alpaca secrets, IAM. image is empty, so no jobs.
#   jobs  — same, plus Cloud Run jobs and Scheduler once image is set.
# Alpaca secret values are not here. The Infra workflow action secrets writes those versions.

data "google_project" "this" {}

locals {
  # One entry per Cloud Run job. args is the moneybot subcommand.
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
  # Google-managed identities. Each one appears only after its API has been used once.
  cloudbuild_sa   = "${data.google_project.this.number}@cloudbuild.gserviceaccount.com"
  scheduler_agent = "serviceAccount:service-${data.google_project.this.number}@gcp-sa-cloudscheduler.iam.gserviceaccount.com"
  # GitHub Actions. Not Owner. The state bucket is created before apply, so this account
  # already needs roles/storage.admin and roles/resourcemanager.projectIamAdmin once, by hand.
  deployer_member = "serviceAccount:${var.deployer_account_id}@${var.project_id}.iam.gserviceaccount.com"
  deployer_roles = toset([
    "roles/serviceusage.serviceUsageAdmin",
    "roles/storage.admin",
    "roles/cloudsql.admin",
    "roles/artifactregistry.admin",
    "roles/run.admin",
    "roles/cloudscheduler.admin",
    "roles/secretmanager.admin",
    "roles/cloudbuild.builds.editor",
    "roles/iam.serviceAccountAdmin",
    "roles/iam.serviceAccountUser",
    "roles/resourcemanager.projectIamAdmin",
  ])
}

# Leave them on if this config is destroyed. Other things in the project may use them.
# iam and cloudresourcemanager must be on before any service account or IAM binding.

resource "google_project_service" "apis" {
  for_each = toset([
    "cloudresourcemanager.googleapis.com",
    "iam.googleapis.com",
    "serviceusage.googleapis.com",
    "run.googleapis.com",
    "sqladmin.googleapis.com",
    "cloudscheduler.googleapis.com",
    "secretmanager.googleapis.com",
    "artifactregistry.googleapis.com",
    "cloudbuild.googleapis.com",
  ])
  service            = each.value
  disable_on_destroy = false
}

resource "google_project_iam_member" "deployer" {
  for_each   = local.deployer_roles
  project    = var.project_id
  role       = each.value
  member     = local.deployer_member
  depends_on = [google_project_service.apis]
}

# Cloud Build pushes bot:latest here. The job service account only pulls.

resource "google_artifact_registry_repository" "bot" {
  location      = var.region
  repository_id = "moneybot"
  format        = "DOCKER"
  depends_on    = [google_project_service.apis]
}

# The job connects through the Cloud SQL volume at /cloudsql, not over the public address.
# The password lives in Secret Manager and also in this state.

resource "random_password" "db" {
  length  = 32
  special = false
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

# Database and user the bot connects as. The password is the random value above.

resource "google_sql_database" "bot" {
  name     = "moneybot"
  instance = google_sql_database_instance.main.name
}

resource "google_sql_user" "bot" {
  name     = "moneybot"
  instance = google_sql_database_instance.main.name
  password = random_password.db.result
}

resource "google_secret_manager_secret" "db_password" {
  secret_id = "moneybot-db-password"
  replication {
    auto {}
  }
  depends_on = [google_project_service.apis]
}

# Terraform writes this version. Alpaca secrets stay empty until the Infra workflow action secrets.

resource "google_secret_manager_secret_version" "db_password" {
  secret      = google_secret_manager_secret.db_password.id
  secret_data = random_password.db.result
}

# Empty shells. The Infra workflow action secrets writes the Alpaca versions. Terraform does not.

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

# job: the Cloud Run process. Reads SQL, secrets, and the image.
# scheduler: Cloud Scheduler calls jobs.run as this account.

resource "google_service_account" "job" {
  account_id   = "moneybot-job"
  display_name = "moneybot Cloud Run job"
  depends_on   = [google_project_service.apis]
}

resource "google_service_account" "scheduler" {
  account_id   = "moneybot-scheduler"
  display_name = "moneybot Cloud Scheduler"
  depends_on   = [google_project_service.apis]
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

# Scheduler's own service agent mints the OAuth token for moneybot-scheduler.
# This agent does not exist until the Scheduler API has been used once. Re-run infra if this 404s.
resource "google_service_account_iam_member" "scheduler_token_creator" {
  service_account_id = google_service_account.scheduler.name
  role               = "roles/iam.serviceAccountTokenCreator"
  member             = local.scheduler_agent
  depends_on         = [google_project_service.apis]
}

# Skipped while var.image is empty. Same image, two jobs: trade and snapshot.

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
        image = var.image
        args  = each.value.args

        env {
          name  = "BOT_CONFIG"
          value = "/app/config/bot.yml"
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

# POST :run with an empty JSON body. OAuth token belongs to moneybot-scheduler.

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

# Pushes the image, then updates a job only if that job already exists.
# serviceAccountUser is required because the job runs as moneybot-job.
# The Cloud Build service account appears after the API is enabled. Re-run infra if this 404s.

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

# Cloud Build writes its own build logs. Without this, the build fails after the push.

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
