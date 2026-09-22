terraform {
  required_version = ">= 1.16, < 2.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.64"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.9"
    }
  }
}

provider "aws" {
  region = "us-east-2"

  default_tags {
    tags = {
      Project     = "shipscope"
      Environment = "prod"
      ManagedBy   = "terraform"
    }
  }
}
