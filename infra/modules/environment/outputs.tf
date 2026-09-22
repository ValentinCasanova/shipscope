output "vpc_id" {
  description = "ID of the environment's VPC."
  value       = aws_vpc.main.id
}

output "public_subnet_ids" {
  description = "Subnets for the API tasks."
  value       = [for subnet in aws_subnet.public : subnet.id]
}

output "private_subnet_ids" {
  description = "Subnets for the internal load balancer and the database."
  value       = [for subnet in aws_subnet.private : subnet.id]
}

output "task_security_group_id" {
  description = "Security group for API tasks, including one-off tasks such as migrations."
  value       = aws_security_group.tasks.id
}

output "database_address" {
  description = "Host name of the database."
  value       = aws_db_instance.main.address
}

output "cluster_name" {
  description = "Name of the ECS cluster."
  value       = aws_ecs_cluster.main.name
}

output "service_name" {
  description = "Name of the API's ECS service."
  value       = aws_ecs_service.api.name
}

output "task_definition_arn" {
  description = "The newest task definition revision, which runs backend_image. Releases run migrations on it and then switch the service to it."
  value       = aws_ecs_task_definition.api.arn
}

output "log_group_name" {
  description = "CloudWatch Logs group of the API and of one-off tasks."
  value       = aws_cloudwatch_log_group.api.name
}

output "load_balancer_dns_name" {
  description = "DNS name of the internal load balancer. It resolves to private addresses only."
  value       = aws_lb.api.dns_name
}
