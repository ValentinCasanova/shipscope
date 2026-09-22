#!/usr/bin/env bash
# Switches the API's ECS service to a task definition revision, the newest one unless
# another is given, and waits until ECS reports the service deployment SUCCESSFUL.
#
# It fails when the deployment circuit breaker rolls the deployment back or ECS stops
# it. Don't replace this with `aws ecs wait services-stable`: after a rollback the old
# tasks are stable again, so that wait reports success.
#
#   infra/scripts/roll-out-backend.sh staging|prod [task definition ARN]

# shellcheck source=lib.sh
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

require_environment "${1:-}" "[task definition ARN]"
target=${2:-$(tf_output task_definition_arn)}
cluster=$(tf_output cluster_name)
service=$(tf_output service_name)

latest_deployment() { # [created after]
  aws ecs list-service-deployments --cluster "$cluster" --service "$service" \
    ${1:+--created-at "after=$1"} \
    --query 'sort_by(serviceDeployments, &createdAt)[-1].serviceDeploymentArn' --output text
}

current=$(aws ecs describe-services --cluster "$cluster" --services "$service" \
  --query 'services[0].taskDefinition' --output text)

if [ "$current" = "$target" ]; then
  # A freshly created service already runs the revision; follow its first deployment.
  log "The service already runs ${target##*/}; checking its latest deployment"
  deployment=$(latest_deployment)
else
  started=$(date -u +%Y-%m-%dT%H:%M:%SZ)
  log "Switching the service from ${current##*/} to ${target##*/}"
  aws ecs update-service --cluster "$cluster" --service "$service" --task-definition "$target" \
    --query 'service.serviceName' --output text >/dev/null
  deployment=None
  for _ in {1..30}; do
    deployment=$(latest_deployment "$started")
    [ "$deployment" = "None" ] || break
    sleep 2
  done
fi
[ "$deployment" != "None" ] || die "couldn't find the service deployment"

deadline=$((SECONDS + 1200))
while :; do
  read -r status reason < <(aws ecs describe-service-deployments --service-deployment-arns "$deployment" \
    --query 'serviceDeployments[0].[status, statusReason]' --output text)
  case "$status" in
    SUCCESSFUL)
      log "Deployment SUCCESSFUL: the service runs ${target##*/}"
      exit 0
      ;;
    ROLLBACK_SUCCESSFUL | ROLLBACK_FAILED | STOPPED)
      die "deployment ended with $status: $reason"
      ;;
  esac
  [ "$SECONDS" -lt "$deadline" ] || die "deployment still $status after 20 minutes"
  log "Deployment $status"
  sleep 15
done
