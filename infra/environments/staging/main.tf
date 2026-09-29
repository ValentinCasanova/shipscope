# Staging: the environment every merge to main deploys to first. It runs the same module
# as prod; the values below are the only differences.
module "environment" {
  source = "../../modules/environment"

  environment   = "staging"
  backend_image = var.backend_image
  vpc_cidr      = "10.10.0.0/16"

  # A subdomain of the domain whose hosted zone infra/bootstrap manages. It stays the same
  # when parking recreates staging.
  domain      = "staging.shipscope.net"
  hosted_zone = "shipscope.net"

  # The staging client of the Google Cloud project. Its secret is in
  # shipscope/staging/integrations.
  google_oauth_client_id = "174117188206-4mermmhom9e13bmhtuub8352unfpj5up.apps.googleusercontent.com"

  deletion_protection         = false
  db_backup_retention_days    = 1
  db_final_snapshot           = false
  secret_recovery_window_days = 0
  log_retention_days          = 14
}
