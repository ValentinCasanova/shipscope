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

output "database_address" {
  description = "Host name of the database."
  value       = module.environment.database_address
}

output "cluster_name" {
  description = "Name of the ECS cluster."
  value       = module.environment.cluster_name
}

output "service_name" {
  description = "Name of the API's ECS service."
  value       = module.environment.service_name
}

output "task_definition_arn" {
  description = "The newest task definition revision. Releases run migrations on it and then switch the service to it."
  value       = module.environment.task_definition_arn
}

output "log_group_name" {
  description = "CloudWatch Logs group of the API and of one-off tasks."
  value       = module.environment.log_group_name
}

output "load_balancer_dns_name" {
  description = "DNS name of the internal load balancer."
  value       = module.environment.load_balancer_dns_name
}

output "cloudfront_domain" {
  description = "The environment's public domain, d….cloudfront.net."
  value       = module.environment.cloudfront_domain
}

output "cloudfront_distribution_id" {
  description = "ID of the CloudFront distribution, for cache invalidations."
  value       = module.environment.cloudfront_distribution_id
}

output "frontend_bucket" {
  description = "S3 bucket that holds the frontend build."
  value       = module.environment.frontend_bucket
}
