output "state_bucket" {
  description = "S3 bucket that holds the Terraform state of every stack."
  value       = aws_s3_bucket.state.bucket
}

output "ecr_repository_url" {
  description = "Registry path for backend images, without a tag or digest."
  value       = aws_ecr_repository.backend.repository_url
}

output "ecr_push_role_arn" {
  description = "Role that builds on main assume to push images. Goes in the ECR_PUSH_ROLE_ARN repository variable."
  value       = aws_iam_role.ecr_push.arn
}

output "deploy_role_arns" {
  description = "Deploy role for each environment. Each goes in its GitHub environment's AWS_DEPLOY_ROLE_ARN variable."
  value       = { for environment, role in aws_iam_role.deploy : environment => role.arn }
}

output "workload_boundary_arn" {
  description = "Permissions boundary that every workload role must carry."
  value       = aws_iam_policy.workload_boundary.arn
}
