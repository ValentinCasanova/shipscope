# State lives in the bucket that infra/bootstrap creates, with a lock file next to it
# while a command runs.
terraform {
  backend "s3" {
    bucket       = "shipscope-tfstate-bf7b3fee"
    key          = "environments/staging/terraform.tfstate"
    region       = "us-east-2"
    encrypt      = true
    use_lockfile = true
  }
}
