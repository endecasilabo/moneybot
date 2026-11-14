# Two applies, same config:
#   infra — registry, BigQuery, empty Alpaca secrets, IAM. image is empty, so no jobs.
#   jobs  — same, plus Cloud Run jobs and Scheduler once image is set.
# Alpaca secret values are not here. The Infra workflow action secrets writes those versions.

data "google_project" "this" {}

locals {
  # One entry per Cloud Run job. args is the moneybot subcommand.
  jobs = {
    snapshot = {
      args = ["snapshot"]
      cron = var.snapshot_cron
    }
    bars = {
      args = ["bars"]
      cron = var.bars_cron
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
    "roles/bigquery.admin",
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
    "bigquery.googleapis.com",
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

# ponytail: API enablement and a new IAM binding are eventually consistent.
# 120s covers the usual delay. A later apply does not wait again. Raise this if a retry still says SERVICE_DISABLED.
resource "time_sleep" "ready" {
  create_duration = "120s"
  depends_on      = [google_project_service.apis, google_project_iam_member.deployer]
}

# Cloud Build pushes {service} and {service}-bedrock here. The job service account only pulls.

resource "google_artifact_registry_repository" "bot" {
  location      = var.region
  repository_id = "moneybot"
  format        = "DOCKER"
  depends_on    = [time_sleep.ready]
}

# Collector tables. The jobs write rows. dbt must not reuse these table ids.
# base_bar column set matches dbt/models/base/base_bar.yml.

locals {
  tables = {
    runs = [
      { name = "id", type = "STRING", mode = "REQUIRED" },
      { name = "job", type = "STRING", mode = "REQUIRED" },
      { name = "status", type = "STRING", mode = "REQUIRED" },
      { name = "detail", type = "STRING" },
      { name = "started_at", type = "TIMESTAMP", mode = "REQUIRED" },
      { name = "finished_at", type = "TIMESTAMP" },
    ]
    signals = [
      { name = "run_id", type = "STRING", mode = "REQUIRED" },
      { name = "symbol", type = "STRING", mode = "REQUIRED" },
      { name = "session_date", type = "DATE", mode = "REQUIRED" },
      { name = "last_price", type = "NUMERIC", mode = "REQUIRED" },
      { name = "sma_trend", type = "FLOAT64" },
      { name = "sma_trend_prev", type = "FLOAT64" },
      { name = "sma_exit", type = "FLOAT64" },
      { name = "trend_ok", type = "BOOL", mode = "REQUIRED" },
      { name = "pullback_ok", type = "BOOL", mode = "REQUIRED" },
      { name = "in_position", type = "BOOL", mode = "REQUIRED" },
      { name = "action", type = "STRING", mode = "REQUIRED" },
      { name = "reason", type = "STRING", mode = "REQUIRED" },
    ]
    orders = [
      { name = "client_order_id", type = "STRING", mode = "REQUIRED" },
      { name = "run_id", type = "STRING", mode = "REQUIRED" },
      { name = "alpaca_order_id", type = "STRING" },
      { name = "symbol", type = "STRING", mode = "REQUIRED" },
      { name = "side", type = "STRING", mode = "REQUIRED" },
      { name = "qty", type = "INT64", mode = "REQUIRED" },
      { name = "time_in_force", type = "STRING", mode = "REQUIRED" },
      { name = "status", type = "STRING" },
      { name = "filled_avg_price", type = "NUMERIC" },
      { name = "error", type = "STRING" },
    ]
    account_snapshots = [
      { name = "run_id", type = "STRING", mode = "REQUIRED" },
      { name = "equity", type = "NUMERIC" },
      { name = "cash", type = "NUMERIC" },
      { name = "buying_power", type = "NUMERIC" },
      { name = "portfolio_value", type = "NUMERIC" },
      { name = "open_orders", type = "JSON", mode = "REQUIRED" },
    ]
    position_snapshots = [
      { name = "run_id", type = "STRING", mode = "REQUIRED" },
      { name = "symbol", type = "STRING", mode = "REQUIRED" },
      { name = "qty", type = "NUMERIC", mode = "REQUIRED" },
      { name = "avg_entry_price", type = "NUMERIC" },
      { name = "market_value", type = "NUMERIC" },
      { name = "unrealized_pl", type = "NUMERIC" },
      { name = "current_price", type = "NUMERIC" },
    ]
    base_bar = [
      { name = "id", type = "STRING", mode = "REQUIRED" },
      { name = "symbol", type = "STRING", mode = "REQUIRED" },
      { name = "feed", type = "STRING", mode = "REQUIRED" },
      { name = "timeframe", type = "STRING", mode = "REQUIRED" },
      { name = "ts", type = "TIMESTAMP", mode = "REQUIRED" },
      { name = "open", type = "NUMERIC", mode = "REQUIRED" },
      { name = "high", type = "NUMERIC", mode = "REQUIRED" },
      { name = "low", type = "NUMERIC", mode = "REQUIRED" },
      { name = "close", type = "NUMERIC", mode = "REQUIRED" },
      { name = "volume", type = "NUMERIC", mode = "REQUIRED" },
      { name = "trade_count", type = "INT64" },
      { name = "vwap", type = "NUMERIC" },
    ]
  }
}

resource "google_bigquery_dataset" "bot" {
  dataset_id = "moneybot"
  location   = var.region
  depends_on = [time_sleep.ready]
}

resource "google_bigquery_table" "bot" {
  for_each            = local.tables
  dataset_id          = google_bigquery_dataset.bot.dataset_id
  table_id            = each.key
  deletion_protection = true
  schema              = jsonencode(each.value)
}

# Empty shells. The Infra workflow action secrets writes the Alpaca versions. Terraform does not.

resource "google_secret_manager_secret" "alpaca_key" {
  secret_id = "moneybot-alpaca-key"
  replication {
    auto {}
  }
  depends_on = [time_sleep.ready]
}

resource "google_secret_manager_secret" "alpaca_secret" {
  secret_id = "moneybot-alpaca-secret"
  replication {
    auto {}
  }
  depends_on = [time_sleep.ready]
}

# job: the Cloud Run process. Writes BigQuery, reads secrets, and pulls the image.
# scheduler: Cloud Scheduler calls jobs.run as this account.

resource "google_service_account" "job" {
  account_id   = "moneybot-job"
  display_name = "moneybot Cloud Run job"
  depends_on   = [time_sleep.ready]
}

resource "google_service_account" "scheduler" {
  account_id   = "moneybot-scheduler"
  display_name = "moneybot Cloud Scheduler"
  depends_on   = [time_sleep.ready]
}

resource "google_bigquery_dataset_iam_member" "job_editor" {
  dataset_id = google_bigquery_dataset.bot.dataset_id
  role       = "roles/bigquery.dataEditor"
  member     = "serviceAccount:${google_service_account.job.email}"
}

resource "google_project_iam_member" "job_bq" {
  project = var.project_id
  role    = "roles/bigquery.jobUser"
  member  = "serviceAccount:${google_service_account.job.email}"
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
  depends_on         = [time_sleep.ready]
}

# Skipped while var.image is empty. Same image, one Cloud Run job per entry in local.jobs.

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
          name  = "GCP_PROJECT"
          value = var.project_id
        }
        env {
          name  = "BQ_DATASET"
          value = google_bigquery_dataset.bot.dataset_id
        }
        env {
          name  = "BQ_LOCATION"
          value = var.region
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
      }
    }
  }

  depends_on = [
    time_sleep.ready,
    google_bigquery_table.bot,
    google_bigquery_dataset_iam_member.job_editor,
    google_project_iam_member.job_bq,
    google_secret_manager_secret_iam_member.job_alpaca_key,
    google_secret_manager_secret_iam_member.job_alpaca_secret,
    google_artifact_registry_repository_iam_member.job_reader,
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
    time_sleep.ready,
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
  depends_on = [time_sleep.ready]
}

resource "google_project_iam_member" "cloudbuild_run" {
  project    = var.project_id
  role       = "roles/run.developer"
  member     = "serviceAccount:${local.cloudbuild_sa}"
  depends_on = [time_sleep.ready]
}

# Cloud Build writes its own build logs. Without this, the build fails after the push.

resource "google_project_iam_member" "cloudbuild_logs" {
  project    = var.project_id
  role       = "roles/logging.logWriter"
  member     = "serviceAccount:${local.cloudbuild_sa}"
  depends_on = [time_sleep.ready]
}

resource "google_service_account_iam_member" "cloudbuild_runs_as_job" {
  service_account_id = google_service_account.job.name
  role               = "roles/iam.serviceAccountUser"
  member             = "serviceAccount:${local.cloudbuild_sa}"
  depends_on         = [time_sleep.ready]
}
