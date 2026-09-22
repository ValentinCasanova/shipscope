# Staging: the environment every merge to main deploys to first. It runs the same module
# as prod; the values below are the only differences.
module "environment" {
  source = "../../modules/environment"

  environment = "staging"
  vpc_cidr    = "10.10.0.0/16"
}
