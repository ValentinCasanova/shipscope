variable "environment" {
  description = "Environment name, used in resource names: staging or prod."
  type        = string

  validation {
    condition     = contains(["staging", "prod"], var.environment)
    error_message = "environment must be staging or prod."
  }
}

variable "vpc_cidr" {
  description = "IPv4 range of the environment's VPC, a /16. Each environment gets its own, so the two can be peered later."
  type        = string

  validation {
    condition     = can(cidrsubnet(var.vpc_cidr, 8, 0)) && endswith(var.vpc_cidr, "/16")
    error_message = "vpc_cidr must be an IPv4 /16, such as 10.10.0.0/16."
  }
}
