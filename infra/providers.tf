# Default provider. Every resource in this directory uses this project and region.

provider "google" {
  project = var.project_id
  region  = var.region
}
