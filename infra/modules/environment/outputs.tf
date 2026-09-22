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
