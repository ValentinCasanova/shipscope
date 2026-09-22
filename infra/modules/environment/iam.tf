# The two roles every API task runs with. Both live under this environment's workload
# path and carry the permissions boundary from infra/bootstrap, the only kind of role
# the deploy roles may create.

data "aws_caller_identity" "current" {}

data "aws_region" "current" {}

locals {
  account_id            = data.aws_caller_identity.current.account_id
  region                = data.aws_region.current.region
  workload_role_path    = "/shipscope-workloads/${var.environment}/"
  workload_boundary_arn = "arn:aws:iam::${local.account_id}:policy/shipscope-workload-boundary"
}

data "aws_iam_policy_document" "ecs_tasks_trust" {
  statement {
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["ecs-tasks.amazonaws.com"]
    }

    # Only ECS acting for this account can assume the role.
    condition {
      test     = "StringEquals"
      variable = "aws:SourceAccount"
      values   = [local.account_id]
    }

    condition {
      test     = "ArnLike"
      variable = "aws:SourceArn"
      values   = ["arn:aws:ecs:${local.region}:${local.account_id}:*"]
    }
  }
}

# Used by ECS itself to start a task: pull the image, send the container's output to
# CloudWatch Logs, and read the secrets it injects.
resource "aws_iam_role" "task_execution" {
  name                 = "${local.name}-task-execution"
  path                 = local.workload_role_path
  description          = "ECS: start ${var.environment} API tasks (image, logs, secrets)"
  assume_role_policy   = data.aws_iam_policy_document.ecs_tasks_trust.json
  permissions_boundary = local.workload_boundary_arn
}

resource "aws_iam_role_policy_attachment" "task_execution" {
  role       = aws_iam_role.task_execution.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

# Add the integrations secret here once the task definition references it (4.0).
data "aws_iam_policy_document" "task_execution_secrets" {
  statement {
    actions = ["secretsmanager:GetSecretValue"]
    resources = [
      aws_secretsmanager_secret.django_secret_key.arn,
      aws_secretsmanager_secret.db_password.arn,
    ]
  }
}

resource "aws_iam_role_policy" "task_execution_secrets" {
  name   = "read-secrets"
  role   = aws_iam_role.task_execution.id
  policy = data.aws_iam_policy_document.task_execution_secrets.json
}

# The application's own permissions. For now it only needs what ECS Exec uses: the
# session channels, and writing the session transcript to the task's log group.
resource "aws_iam_role" "task" {
  name                 = "${local.name}-task"
  path                 = local.workload_role_path
  description          = "The ${var.environment} API's own permissions (ECS Exec)"
  assume_role_policy   = data.aws_iam_policy_document.ecs_tasks_trust.json
  permissions_boundary = local.workload_boundary_arn
}

data "aws_iam_policy_document" "task" {
  statement {
    sid = "OpenEcsExecChannels"
    actions = [
      "ssmmessages:CreateControlChannel",
      "ssmmessages:CreateDataChannel",
      "ssmmessages:OpenControlChannel",
      "ssmmessages:OpenDataChannel",
    ]
    resources = ["*"]
  }

  statement {
    sid = "WriteEcsExecTranscripts"
    actions = [
      "logs:CreateLogStream",
      "logs:DescribeLogStreams",
      "logs:PutLogEvents",
    ]
    resources = [aws_cloudwatch_log_group.api.arn, "${aws_cloudwatch_log_group.api.arn}:*"]
  }

  statement {
    sid       = "FindLogGroups"
    actions   = ["logs:DescribeLogGroups"]
    resources = ["*"]
  }
}

resource "aws_iam_role_policy" "task" {
  name   = "ecs-exec"
  role   = aws_iam_role.task.id
  policy = data.aws_iam_policy_document.task.json
}
