# What the CI roles from github-oidc.tf may do, and the permissions boundary
# that caps every role the environment stacks create. Only this stack, applied
# with your own credentials, can change any of it.

data "aws_caller_identity" "current" {}

data "aws_region" "current" {}

locals {
  account_id = data.aws_caller_identity.current.account_id
  region     = data.aws_region.current.region
}

# Build: push backend images.

data "aws_iam_policy_document" "ecr_push" {
  # Signing in to the registry. This action can't be limited to a repository.
  statement {
    sid       = "GetRegistryToken"
    actions   = ["ecr:GetAuthorizationToken"]
    resources = ["*"]
  }

  # Immutable tags reject a second push of the same tag, so a re-run looks up
  # the image its first run pushed (DescribeImages) instead of pushing again.
  statement {
    sid = "PushAndPullBackendImages"
    actions = [
      "ecr:BatchCheckLayerAvailability",
      "ecr:BatchGetImage",
      "ecr:CompleteLayerUpload",
      "ecr:DescribeImages",
      "ecr:GetDownloadUrlForLayer",
      "ecr:InitiateLayerUpload",
      "ecr:PutImage",
      "ecr:UploadLayerPart",
    ]
    resources = [aws_ecr_repository.backend.arn]
  }
}

resource "aws_iam_role_policy" "ecr_push" {
  name   = "push-backend-images"
  role   = aws_iam_role.ecr_push.id
  policy = data.aws_iam_policy_document.ecr_push.json
}

# Deploy: apply an environment stack and run its tasks.

# Everything except IAM, AWS Organizations, and account settings. Terraform
# needs this breadth to manage an environment. Within one AWS account it also
# lets either deploy role change the other environment's non-IAM resources.
resource "aws_iam_role_policy_attachment" "deploy_power_user" {
  for_each = aws_iam_role.deploy

  role       = each.value.name
  policy_arn = "arn:aws:iam::aws:policy/PowerUserAccess"
}

# The IAM rights an environment stack needs for its task roles. Each deploy role
# may manage only roles under its own environment's path, and may create a role
# or change its permissions only with the workload boundary attached, so no role
# it creates can do more than the boundary allows. It has no rights on the CI
# roles, including itself, or on the boundary policy.
data "aws_iam_policy_document" "deploy_workload_roles" {
  for_each = aws_iam_role.deploy

  statement {
    sid = "ChangePermissionsOnlyWithBoundary"
    actions = [
      "iam:AttachRolePolicy",
      "iam:CreateRole",
      "iam:DeleteRolePolicy",
      "iam:DetachRolePolicy",
      "iam:PutRolePermissionsBoundary",
      "iam:PutRolePolicy",
    ]
    resources = ["arn:aws:iam::${local.account_id}:role/shipscope-workloads/${each.key}/*"]

    condition {
      test     = "StringEquals"
      variable = "iam:PermissionsBoundary"
      values   = [aws_iam_policy.workload_boundary.arn]
    }
  }

  statement {
    sid = "ManageWorkloadRoles"
    actions = [
      "iam:DeleteRole",
      "iam:GetRole",
      "iam:GetRolePolicy",
      "iam:ListAttachedRolePolicies",
      "iam:ListInstanceProfilesForRole",
      "iam:ListRolePolicies",
      "iam:ListRoleTags",
      "iam:TagRole",
      "iam:UntagRole",
      "iam:UpdateAssumeRolePolicy",
      "iam:UpdateRole",
    ]
    resources = ["arn:aws:iam::${local.account_id}:role/shipscope-workloads/${each.key}/*"]
  }

  # Registering a task definition or running a task hands its roles to ECS.
  statement {
    sid       = "PassWorkloadRolesToEcsTasks"
    actions   = ["iam:PassRole"]
    resources = ["arn:aws:iam::${local.account_id}:role/shipscope-workloads/${each.key}/*"]

    condition {
      test     = "StringEquals"
      variable = "iam:PassedToService"
      values   = ["ecs-tasks.amazonaws.com"]
    }
  }
}

resource "aws_iam_role_policy" "deploy_workload_roles" {
  for_each = aws_iam_role.deploy

  name   = "manage-workload-roles"
  role   = each.value.id
  policy = data.aws_iam_policy_document.deploy_workload_roles[each.key].json
}

# Workloads: the most any task role may ever do. A role's effective permissions
# are the overlap of its own policies and this boundary, whatever policies
# Terraform attaches to it.

data "aws_iam_policy_document" "workload_boundary" {
  statement {
    sid       = "GetRegistryToken"
    actions   = ["ecr:GetAuthorizationToken"]
    resources = ["*"]
  }

  statement {
    sid = "PullBackendImages"
    actions = [
      "ecr:BatchCheckLayerAvailability",
      "ecr:BatchGetImage",
      "ecr:GetDownloadUrlForLayer",
    ]
    resources = [aws_ecr_repository.backend.arn]
  }

  # Container logs and ECS Exec session logs, in each environment's
  # /ecs/shipscope-<environment> log group.
  statement {
    sid = "WriteLogs"
    actions = [
      "logs:CreateLogStream",
      "logs:DescribeLogStreams",
      "logs:PutLogEvents",
    ]
    resources = ["arn:aws:logs:${local.region}:${local.account_id}:log-group:/ecs/shipscope-*"]
  }

  statement {
    sid       = "FindLogGroups"
    actions   = ["logs:DescribeLogGroups"]
    resources = ["*"]
  }

  statement {
    sid       = "ReadSecrets"
    actions   = ["secretsmanager:GetSecretValue"]
    resources = ["arn:aws:secretsmanager:${local.region}:${local.account_id}:secret:shipscope/*"]
  }

  # The channels that carry an ECS Exec shell session.
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
}

resource "aws_iam_policy" "workload_boundary" {
  name        = "shipscope-workload-boundary"
  description = "Permissions boundary for every ShipScope workload role"
  policy      = data.aws_iam_policy_document.workload_boundary.json
}
