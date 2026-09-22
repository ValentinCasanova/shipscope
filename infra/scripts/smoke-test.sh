#!/usr/bin/env bash
# Checks an environment through CloudFront: the API and its database report ok, and the
# app's HTML is served. Retries for up to 5 minutes, since a fresh deploy can take a
# moment to become reachable.
#
#   infra/scripts/smoke-test.sh staging|prod

# shellcheck source=lib.sh
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

require_environment "${1:-}"
url="https://$(tf_output cloudfront_domain)"

deadline=$((SECONDS + 300))
until health=$(curl -fsS --max-time 10 "$url/api/health/" 2>/dev/null) &&
  jq -e '.status == "ok" and .database == "ok"' <<<"$health" >/dev/null 2>&1; do
  [ "$SECONDS" -lt "$deadline" ] || die "$url/api/health/ didn't report ok within 5 minutes: ${health:-no response}"
  log "API not ok yet (${health:-no response}); retrying"
  sleep 10
done
log "API: $health"

curl -fsS --max-time 10 "$url/" | grep -q '<div id="root"></div>' ||
  die "$url/ didn't return the app's HTML"
log "Smoke test passed: $url"
