#!/usr/bin/env bash
# Sets one key in an environment's integrations secret, the JSON object of third-party API
# keys that the API reads, such as GOOGLE_OAUTH_CLIENT_SECRET. Asks for the value without
# showing it, and keeps the secret's other keys. The value never appears on a command
# line, where the process list would show it, or in your shell history.
#
#   infra/scripts/set-integration-key.sh staging|prod <KEY>
#
# Tasks read secrets when they start, so the API gets the new value with the next release
# or rollout.

# shellcheck source=lib.sh
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

require_environment "${1:-}" "<KEY>"
key=${2:-}
[[ $key =~ ^[A-Z][A-Z0-9_]*$ ]] || die "usage: $(basename "$0") staging|prod <KEY>, with a KEY such as GOOGLE_OAUTH_CLIENT_SECRET"
secret_id="shipscope/$ENVIRONMENT/integrations"

# The keys set so far. A secret that has never had a value has none.
if ! current=$(aws secretsmanager get-secret-value --secret-id "$secret_id" \
  --query SecretString --output text 2>&1); then
  [[ $current == *"can't find the specified secret value"* ]] || die "couldn't read $secret_id: $current"
  current='{}'
fi

read -rsp "Value of $key for $secret_id (input hidden): " value
echo >&2
[ -n "$value" ] || die "the value is empty"

# jq reads the value from its environment, and the AWS CLI reads the new JSON from a pipe.
json=$(VALUE=$value jq -c --arg key "$key" '. + {($key): env.VALUE}' <<<"$current")
version=$(printf '%s' "$json" | aws secretsmanager put-secret-value --secret-id "$secret_id" \
  --secret-string file:///dev/stdin --query VersionId --output text)
log "Stored $key in $secret_id as version $version. Its keys: $(jq -r 'keys | join(", ")' <<<"$json")"
