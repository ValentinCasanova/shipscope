# The deploy scripts in infra/scripts read these with `terraform output`.

output "vpc_id" {
  description = "ID of the environment's VPC."
  value       = module.environment.vpc_id
}

output "public_subnet_ids" {
  description = "Subnets for the API tasks."
  value       = module.environment.public_subnet_ids
}

output "private_subnet_ids" {
  description = "Subnets for the internal load balancer and the database."
  value       = module.environment.private_subnet_ids
}

output "task_security_group_id" {
  description = "Security group for API tasks, including one-off tasks such as migrations."
  value       = module.environment.task_security_group_id
}
