# Terraform generates the Django secret key and the database password as ephemeral
# values and writes them through write-only arguments, so neither is ever stored in the
# state or shown in a plan. ECS reads the secrets when a task starts.
#
# A new value is generated on every run but only written when its version below goes
# up. To rotate one, raise its version and apply; the database password then changes
# in the secret and in RDS in the same run. Running tasks keep the old value until they
# are replaced, so roll out the service afterwards.
#
# RDS takes its password from the secret (below), not from the generated value directly.
# That way an apply always gives the database the password the tasks are handed, even
# when a previous run was interrupted between writing the secret and creating the
# database, or when the database is imported into a new state.

locals {
  django_secret_key_version = 1
  db_password_version       = 1
}

ephemeral "random_password" "django_secret_key" {
  length  = 64
  special = false
}

ephemeral "random_password" "db_password" {
  length  = 40
  special = false
}

resource "aws_secretsmanager_secret" "django_secret_key" {
  name                    = "shipscope/${var.environment}/django-secret-key"
  description             = "Django SECRET_KEY for the ${var.environment} API"
  recovery_window_in_days = var.secret_recovery_window_days
}

resource "aws_secretsmanager_secret_version" "django_secret_key" {
  secret_id                = aws_secretsmanager_secret.django_secret_key.id
  secret_string_wo         = ephemeral.random_password.django_secret_key.result
  secret_string_wo_version = local.django_secret_key_version
}

resource "aws_secretsmanager_secret" "db_password" {
  name                    = "shipscope/${var.environment}/db-password"
  description             = "Password of the ${var.environment} database's master user"
  recovery_window_in_days = var.secret_recovery_window_days
}

resource "aws_secretsmanager_secret_version" "db_password" {
  secret_id                = aws_secretsmanager_secret.db_password.id
  secret_string_wo         = ephemeral.random_password.db_password.result
  secret_string_wo_version = local.db_password_version
}

ephemeral "aws_secretsmanager_secret_version" "db_password" {
  secret_id = aws_secretsmanager_secret.db_password.id

  # Read the value only after this run has written it, if the version went up.
  depends_on = [aws_secretsmanager_secret_version.db_password]
}

# EasyPost, Google, and Anthropic keys, as fields of one JSON object, set by hand in
# 4.0, 5.0, and 8.0 with `aws secretsmanager put-secret-value`. Terraform creates the
# secret without a value, so it can never overwrite the keys.
resource "aws_secretsmanager_secret" "integrations" {
  name                    = "shipscope/${var.environment}/integrations"
  description             = "Third-party API keys for the ${var.environment} API, as JSON"
  recovery_window_in_days = var.secret_recovery_window_days
}
