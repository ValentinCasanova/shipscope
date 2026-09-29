# Terraform generates the Django secret key, the database password, and the token
# encryption key as ephemeral values and writes them through write-only arguments, so
# none of them is ever stored in the state or shown in a plan. ECS reads the secrets when
# a task starts.
#
# A new value is generated on every run but only written when its version below goes
# up. To rotate one, raise its version and apply; the database password then changes
# in the secret and in RDS in the same run. Running tasks keep the old value until they
# are replaced, so roll out the service afterwards. Rotating the token encryption key
# makes every stored Google token unreadable, and users then have to connect Google
# Drive again.
#
# RDS takes its password from the secret (below), not from the generated value directly.
# That way an apply always gives the database the password the tasks are handed, even
# when a previous run was interrupted between writing the secret and creating the
# database, or when the database is imported into a new state.

locals {
  django_secret_key_version    = 1
  db_password_version          = 1
  token_encryption_key_version = 1
}

ephemeral "random_password" "django_secret_key" {
  length  = 64
  special = false
}

ephemeral "random_password" "db_password" {
  length  = 40
  special = false
}

ephemeral "random_password" "token_encryption_key" {
  length  = 64
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

# The API derives the key that encrypts users' Google tokens in the database from this
# value (4.1.2), so a database dump or backup holds only ciphertext.
resource "aws_secretsmanager_secret" "token_encryption_key" {
  name                    = "shipscope/${var.environment}/token-encryption-key"
  description             = "Key material that encrypts the ${var.environment} API's stored Google tokens"
  recovery_window_in_days = var.secret_recovery_window_days
}

resource "aws_secretsmanager_secret_version" "token_encryption_key" {
  secret_id                = aws_secretsmanager_secret.token_encryption_key.id
  secret_string_wo         = ephemeral.random_password.token_encryption_key.result
  secret_string_wo_version = local.token_encryption_key_version
}

# Third-party API keys, such as the Google OAuth client secret, as fields of one JSON
# object that you set by hand. infra/bootstrap creates the secret, so parking staging
# keeps it; this stack only looks it up.
data "aws_secretsmanager_secret" "integrations" {
  name = "shipscope/${var.environment}/integrations"
}

# Until 4.0 this stack created the secret. Forget it without deleting it, now that
# infra/bootstrap manages it.
removed {
  from = aws_secretsmanager_secret.integrations

  lifecycle {
    destroy = false
  }
}
