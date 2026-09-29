# Prod: the public portfolio URL, deployed after you approve a release that staging has
# already run. It runs the same module as staging; the values below are the only
# differences. Apart from its domain and Google client, each one protects data or keeps
# it longer.
module "environment" {
  source = "../../modules/environment"

  environment   = "prod"
  backend_image = var.backend_image
  vpc_cidr      = "10.20.0.0/16"

  # The apex of the domain whose hosted zone infra/bootstrap manages.
  domain      = "shipscope.net"
  hosted_zone = "shipscope.net"

  # The prod client of the Google Cloud project. Its secret is in
  # shipscope/prod/integrations.
  google_oauth_client_id = "174117188206-5jtvoum1dcia2s2ophdqjjj6b3voh9t1.apps.googleusercontent.com"

  deletion_protection         = true
  db_backup_retention_days    = 7
  db_final_snapshot           = true
  secret_recovery_window_days = 7
  log_retention_days          = 30
}
