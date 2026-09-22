# The API on ECS Fargate: one task, behind the internal load balancer in alb.tf.
#
# A release doesn't restart anything when Terraform applies. The apply registers a new
# task definition revision for the new image; infra/scripts runs migrations on that
# revision as a one-off task, then switches the service to it.

resource "aws_ecs_cluster" "main" {
  name = local.name

  setting {
    name  = "containerInsights"
    value = "disabled"
  }
}

resource "aws_cloudwatch_log_group" "api" {
  name              = "/ecs/${local.name}"
  retention_in_days = var.log_retention_days
}

locals {
  api_environment = {
    DJANGO_DEBUG             = "false"
    DJANGO_ALLOWED_HOSTS     = ""
    DJANGO_BEHIND_CLOUDFRONT = "false"
    DJANGO_LOG_FORMAT        = "json"
    POSTGRES_HOST            = aws_db_instance.main.address
    POSTGRES_PORT            = tostring(aws_db_instance.main.port)
    POSTGRES_DB              = aws_db_instance.main.db_name
    POSTGRES_USER            = aws_db_instance.main.username
    POSTGRES_SSLMODE         = "require"
    WEB_CONCURRENCY          = "2"
  }
}

resource "aws_ecs_task_definition" "api" {
  family                   = "${local.name}-api"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = 256
  memory                   = 512
  execution_role_arn       = aws_iam_role.task_execution.arn
  task_role_arn            = aws_iam_role.task.arn

  runtime_platform {
    operating_system_family = "LINUX"
    cpu_architecture        = "X86_64"
  }

  container_definitions = jsonencode([
    {
      name         = "api"
      image        = var.backend_image
      essential    = true
      portMappings = [{ containerPort = 8000, protocol = "tcp" }]
      environment  = [for name, value in local.api_environment : { name = name, value = value }]
      secrets = [
        { name = "DJANGO_SECRET_KEY", valueFrom = aws_secretsmanager_secret.django_secret_key.arn },
        { name = "POSTGRES_PASSWORD", valueFrom = aws_secretsmanager_secret.db_password.arn },
      ]
      logConfiguration = {
        logDriver = "awslogs"
        options = {
          awslogs-group         = aws_cloudwatch_log_group.api.name
          awslogs-region        = local.region
          awslogs-stream-prefix = "api"
        }
      }
      # An init process reaps the processes that ECS Exec sessions start.
      linuxParameters = { initProcessEnabled = true }
    },
  ])

  # Keep old revisions registered when a new one replaces them, so a rollback can use
  # them.
  skip_destroy = true

  # The secret values must exist before a task can start with this revision.
  depends_on = [
    aws_secretsmanager_secret_version.django_secret_key,
    aws_secretsmanager_secret_version.db_password,
  ]
}

resource "aws_ecs_service" "api" {
  name                   = "${local.name}-api"
  cluster                = aws_ecs_cluster.main.id
  task_definition        = aws_ecs_task_definition.api.arn
  desired_count          = 1
  launch_type            = "FARGATE"
  platform_version       = "LATEST"
  enable_execute_command = true

  # Tag tasks like the service, so Cost Explorer can split Fargate costs by environment.
  enable_ecs_managed_tags = true
  propagate_tags          = "SERVICE"

  # Public IPs only for outbound calls; the security group admits only the load
  # balancer.
  network_configuration {
    subnets          = [for subnet in aws_subnet.public : subnet.id]
    security_groups  = [aws_security_group.tasks.id]
    assign_public_ip = true
  }

  load_balancer {
    target_group_arn = aws_lb_target_group.api.arn
    container_name   = "api"
    container_port   = 8000
  }

  # Start the new task before stopping the old one, and roll back automatically when
  # new tasks keep failing.
  deployment_minimum_healthy_percent = 100
  deployment_maximum_percent         = 200
  health_check_grace_period_seconds  = 60

  deployment_circuit_breaker {
    enable   = true
    rollback = true
  }

  # infra/scripts/roll-out-backend.sh moves the service to a new revision.
  lifecycle {
    ignore_changes = [task_definition]
  }

  # The target group must belong to a load balancer before a service can use it.
  depends_on = [aws_lb_listener.http]
}
