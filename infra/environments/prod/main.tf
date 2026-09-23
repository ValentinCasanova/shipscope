# Prod: the public portfolio URL, deployed after you approve a release that staging has
# already run. It runs the same module as staging; the values below are the only
# differences, and each one protects data or keeps it longer.
module "environment" {
  source = "../../modules/environment"

  environment   = "prod"
  backend_image = var.backend_image
  vpc_cidr      = "10.20.0.0/16"

  deletion_protection         = true
  db_backup_retention_days    = 7
  db_final_snapshot           = true
  secret_recovery_window_days = 7
  log_retention_days          = 30
}
