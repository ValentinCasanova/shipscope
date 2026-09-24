#!/usr/bin/env bash
# Runs Django's migrations as a one-off Fargate task on the newest task definition
# revision, prints the task's output, and fails unless the migrations succeed. Releases
# run this before the service switches to that revision, so new code never runs against
# an old schema, and the deploy log lists each migration the release applied.
#
#   infra/scripts/run-migrations.sh staging|prod [migrate arguments]
#
# Extra arguments go to `manage.py migrate`, such as an app label. To run on another
# revision, such as the one the service runs, set TASK_DEFINITION to its ARN.

# shellcheck source=lib.sh
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

require_environment "${1:-}" "[migrate arguments]"
shift

cluster=$(tf_output cluster_name)
task_definition=${TASK_DEFINITION:-$(tf_output task_definition_arn)}
subnets=$(tf_output_json public_subnet_ids | jq -r 'join(",")')
security_group=$(tf_output task_security_group_id)
log_group=$(tf_output log_group_name)

# The -- keeps jq from reading migrate's options, such as --plan, as its own.
overrides=$(jq -n '{containerOverrides: [{name: "api", command: (["python", "manage.py", "migrate", "--noinput"] + $ARGS.positional)}]}' --args -- "$@")

log "Running migrate${*:+ $*} on ${task_definition##*/}"
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

# CloudWatch Logs can receive a stopped task's last lines a few seconds late, so read the
# log until two reads in a row return the same lines. After a success, the output holds
# only Django's progress messages, such as `Applying accounts.0001_initial... OK`, so it's
# safe in the public deploy log.
output=""
for _ in {1..8}; do
  previous=$output
  output=$(aws logs get-log-events --log-group-name "$log_group" --log-stream-name "api/api/$task_id" \
    --start-from-head --query 'events[].message' --output json 2>/dev/null | jq -r '.[]') || output=""
  if [ -n "$output" ] && [ "$output" = "$previous" ]; then
    break
  fi
  sleep 3
done
output=${output:-(CloudWatch Logs has no output from the task)}

if [ "$exit_code" != "0" ]; then
  log "Migrations failed: exit code $exit_code ($stopped_reason). The task's output:"
  printf '%s\n' "$output" >&2
  exit 1
fi
log "Migrations finished. The task's output:"
printf '%s\n' "$output" >&2
