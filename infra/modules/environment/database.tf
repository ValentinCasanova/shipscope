# PostgreSQL on RDS, in the private subnets, reachable only from the API tasks' security
# group. The default parameter group for PostgreSQL 17 sets rds.force_ssl to 1, so the
# server refuses unencrypted connections, and the tasks connect with sslmode=require.

resource "aws_db_subnet_group" "main" {
  name        = local.name
  description = "Private subnets for the ${var.environment} database"
  subnet_ids  = [for subnet in aws_subnet.private : subnet.id]
}

resource "aws_db_instance" "main" {
  identifier = local.name

  engine = "postgres"
  # Only the major version, matching postgres:17 locally. RDS picks the minor version
  # and applies minor upgrades in the maintenance window.
  engine_version             = "17"
  auto_minor_version_upgrade = true
  # Stop instead of paying for RDS Extended Support when version 17 reaches its end of
  # standard support.
  engine_lifecycle_support = "open-source-rds-extended-support-disabled"
  instance_class           = "db.t4g.micro"

  allocated_storage = 20
  storage_type      = "gp3"
  storage_encrypted = true

  db_name             = "shipscope"
  username            = "shipscope"
  password_wo         = ephemeral.random_password.db_password.result
  password_wo_version = local.db_password_version

  db_subnet_group_name   = aws_db_subnet_group.main.name
  vpc_security_group_ids = [aws_security_group.database.id]
  publicly_accessible    = false
  multi_az               = false

  backup_retention_period   = var.db_backup_retention_days
  copy_tags_to_snapshot     = true
  skip_final_snapshot       = !var.db_final_snapshot
  final_snapshot_identifier = var.db_final_snapshot ? "${local.name}-final" : null
  deletion_protection       = var.deletion_protection

  # Changes such as a new password take effect now, not in the next maintenance window.
  apply_immediately = true
}
