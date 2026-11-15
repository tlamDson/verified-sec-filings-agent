# One free-plan project: Postgres 17, the smallest compute that scales to zero, and the
# free plan's longest history window (6 hours). pgvector and pg_search are created by SQL
# (infra/postgres/init/01-extensions.sql), not here.
resource "neon_project" "main" {
  name                      = var.neon_project_name
  org_id                    = var.neon_org_id
  region_id                 = var.neon_region
  pg_version                = 17
  history_retention_seconds = 21600

  branch {
    name          = "main"
    database_name = "sec"
    role_name     = "sec"
  }

  primary_compute {
    autoscaling_limit_min_cu = 0.25
    autoscaling_limit_max_cu = 1
    suspend_timeout_seconds  = 300
  }
}
