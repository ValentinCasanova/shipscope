# Shared by the deploy scripts in this folder; each one sources it.
# shellcheck shell=bash

set -euo pipefail

SCRIPTS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INFRA_DIR="$(dirname "$SCRIPTS_DIR")"

log() {
  printf '%s  %s\n' "$(date -u +%H:%M:%S)" "$*" >&2
}

die() {
  log "error: $*"
  exit 1
}

# Checks the environment argument and sets ENVIRONMENT. The second argument describes
# the script's other arguments, for the usage message.
require_environment() {
  case "${1:-}" in
    staging | prod) ENVIRONMENT="$1" ;;
    *) die "usage: $(basename "$0") staging|prod ${2:-}" ;;
  esac
}

# Prints one of the environment's Terraform outputs. The root must be initialized.
tf_output() {
  terraform -chdir="$INFRA_DIR/environments/$ENVIRONMENT" output -raw "$1"
}

# Same, for list and map outputs, as JSON.
tf_output_json() {
  terraform -chdir="$INFRA_DIR/environments/$ENVIRONMENT" output -json "$1"
}
