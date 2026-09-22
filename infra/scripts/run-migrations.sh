#!/usr/bin/env bash
# Runs Django's migrations as a one-off Fargate task on the newest task definition
# revision, and fails unless they succeed. Releases run this before the service switches
# to that revision, so new code never runs against an old schema.
#
#   infra/scripts/run-migrations.sh staging|prod [migrate arguments]
#
# Extra arguments go to `manage.py migrate`, such as an app label.

# shellcheck source=lib.sh
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

require_environment "${1:-}" "[migrate arguments]"
shift

cluster=$(tf_output cluster_name)
task_definition=$(tf_output task_definition_arn)
subnets=$(tf_output_json public_subnet_ids | jq -r 'join(",")')
security_group=$(tf_output task_security_group_id)
log_group=$(tf_output log_group_name)

overrides=$(jq -n '{containerOverrides: [{name: "api", command: (["python", "manage.py", "migrate", "--noinput"] + $ARGS.positional)}]}' --args "$@")

log "Running migrations on ${task_definition##*/}"
task_arn=$(aws ecs run-task \
  --cluster "$cluster" \
  --task-definition "$task_definition" \
  --launch-type FARGATE \
  --network-configuration "awsvpcConfiguration={subnets=[$subnets],securityGroups=[$security_group],assignPublicIp=ENABLED}" \
  --overrides "$overrides" \
  --started-by run-migrations \
  --query 'tasks[0].taskArn' --output text)
[ "$task_arn" != "None" ] || die "ECS didn't start the migration task"
task_id=${task_arn##*/}
log "Task $task_id started; waiting for it to stop"

# Polls every 6 seconds, for up to 10 minutes.
aws ecs wait tasks-stopped --cluster "$cluster" --tasks "$task_arn" ||
  die "task $task_id didn't stop within 10 minutes"

read -r exit_code stopped_reason < <(aws ecs describe-tasks --cluster "$cluster" --tasks "$task_arn" \
  --query "tasks[0].[containers[?name=='api'].exitCode | [0], stoppedReason]" --output text)

if [ "$exit_code" != "0" ]; then
  log "Migrations failed: exit code $exit_code ($stopped_reason). The task's output:"
  aws logs get-log-events --log-group-name "$log_group" --log-stream-name "api/api/$task_id" \
    --start-from-head --query 'events[].message' --output json | jq -r '.[]' >&2 || true
  exit 1
fi
log "Migrations finished"
