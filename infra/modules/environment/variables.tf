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

# Safety settings that differ between staging and prod. Staging can be destroyed and
# recreated between work sessions; prod can't be deleted by accident.

variable "deletion_protection" {
  description = "Whether AWS refuses to delete the database and the load balancer."
  type        = bool
}

variable "db_backup_retention_days" {
  description = "Days of automated database backups to keep."
  type        = number
}

variable "db_final_snapshot" {
  description = "Whether destroying the database first takes a final snapshot."
  type        = bool
}

variable "secret_recovery_window_days" {
  description = "Days a deleted secret can be restored: 0, or 7 to 30. 0 lets a destroyed environment be recreated at once with the same secret names."
  type        = number

  validation {
    condition     = var.secret_recovery_window_days == 0 || (var.secret_recovery_window_days >= 7 && var.secret_recovery_window_days <= 30)
    error_message = "secret_recovery_window_days must be 0 or between 7 and 30."
  }
}
