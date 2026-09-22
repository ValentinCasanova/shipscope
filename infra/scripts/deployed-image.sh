#!/usr/bin/env bash
# Prints the image the environment's API service runs, as <repository>@sha256:<digest>.
# Pass it to a local plan, so Terraform doesn't want to register a different image:
#
#   terraform -chdir=infra/environments/staging plan \
#     -var "backend_image=$(infra/scripts/deployed-image.sh staging)"

# shellcheck source=lib.sh
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

require_environment "${1:-}"
cluster=$(tf_output cluster_name)
service=$(tf_output service_name)

task_definition=$(aws ecs describe-services --cluster "$cluster" --services "$service" \
  --query 'services[0].taskDefinition' --output text)
aws ecs describe-task-definition --task-definition "$task_definition" \
  --query "taskDefinition.containerDefinitions[?name=='api'].image | [0]" --output text
