# GitHub Actions signs in to AWS with short-lived OIDC tokens, so GitHub stores
# no AWS keys. A role accepts a token only if its audience is STS and its
# subject names this repository and the exact branch or GitHub environment the
# job runs for. The roles' permissions are in iam.tf.

resource "aws_iam_openid_connect_provider" "github" {
  url            = "https://token.actions.githubusercontent.com"
  client_id_list = ["sts.amazonaws.com"]
}

locals {
  github_subject_prefix = "repo:${var.github_owner}@${var.github_owner_id}/${var.github_repository}@${var.github_repository_id}"

  # The one token subject each CI role accepts. A job that names a GitHub
  # environment gets environment:<name> in its subject instead of its branch.
  ci_role_subjects = {
    ecr_push = "${local.github_subject_prefix}:ref:refs/heads/main"
    staging  = "${local.github_subject_prefix}:environment:staging"
    prod     = "${local.github_subject_prefix}:environment:prod"
  }
}

data "aws_iam_policy_document" "github_trust" {
  for_each = local.ci_role_subjects

  statement {
    actions = ["sts:AssumeRoleWithWebIdentity"]

    principals {
      type        = "Federated"
      identifiers = [aws_iam_openid_connect_provider.github.arn]
    }

    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:aud"
      values   = ["sts.amazonaws.com"]
    }

    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:sub"
      values   = [each.value]
    }
  }
}

resource "aws_iam_role" "ecr_push" {
  name                 = "shipscope-ecr-push"
  path                 = "/shipscope-ci/"
  description          = "GitHub Actions: push backend images from builds on main"
  assume_role_policy   = data.aws_iam_policy_document.github_trust["ecr_push"].json
  max_session_duration = 7200
}

resource "aws_iam_role" "deploy" {
  for_each = toset(["staging", "prod"])

  name                 = "shipscope-${each.key}-deploy"
  path                 = "/shipscope-ci/"
  description          = "GitHub Actions: deploy the ${each.key} environment"
  assume_role_policy   = data.aws_iam_policy_document.github_trust[each.key].json
  max_session_duration = 7200
}
