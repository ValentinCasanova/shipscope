# The bucket that state.tf creates. The first apply of this stack ran with local state
# and then moved it here; infra/README.md describes how to do that in a new account.
terraform {
  backend "s3" {
    bucket       = "shipscope-tfstate-bf7b3fee"
    key          = "bootstrap/terraform.tfstate"
    region       = "us-east-2"
    encrypt      = true
    use_lockfile = true
  }
}
