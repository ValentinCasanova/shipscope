# Each environment's third-party API keys, as fields of one JSON object: the Google OAuth
# client secret since 4.0, and later the EasyPost and Anthropic keys. You set them by
# hand (infra/README.md). Terraform creates the secrets without a value, so it can never
# overwrite a key.
#
# They live here rather than in the environment stack so that parking staging keeps
# them. A task can't start while its task definition names a key that its secret lacks,
# so a recreated staging with an empty secret would stop at its first release's
# migrations.

resource "aws_secretsmanager_secret" "integrations" {
  for_each = toset(["staging", "prod"])

  name                    = "shipscope/${each.key}/integrations"
  description             = "Third-party API keys for the ${each.key} API, as JSON"
  recovery_window_in_days = 7

  # Cost Explorer then counts the secret with its environment, not the shared stack.
  tags = { Environment = each.key }
}
