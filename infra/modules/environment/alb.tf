# An internal Application Load Balancer in the private subnets. Only CloudFront reaches
# it, through a VPC origin (cdn.tf), so it listens on plain HTTP: CloudFront handles
# HTTPS for the browser.

resource "aws_lb" "api" {
  name               = "${local.name}-api"
  internal           = true
  load_balancer_type = "application"
  subnets            = [for subnet in aws_subnet.private : subnet.id]
  security_groups    = [aws_security_group.alb.id]

  drop_invalid_header_fields = true
  enable_deletion_protection = var.deletion_protection
}

resource "aws_lb_target_group" "api" {
  name        = "${local.name}-api"
  port        = 8000
  protocol    = "HTTP"
  target_type = "ip"
  vpc_id      = aws_vpc.main.id

  # A stopping task gets 30 seconds to finish its requests, instead of the default 300.
  deregistration_delay = 30

  # The timeout is longer than the 5-second connect_timeout Django uses for the
  # database, so a slow or unreachable database doesn't make healthy tasks look dead.
  health_check {
    path                = "/api/health/"
    matcher             = "200"
    interval            = 15
    timeout             = 10
    healthy_threshold   = 2
    unhealthy_threshold = 3
  }
}

resource "aws_lb_listener" "http" {
  load_balancer_arn = aws_lb.api.arn
  port              = 80
  protocol          = "HTTP"

  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.api.arn
  }
}
