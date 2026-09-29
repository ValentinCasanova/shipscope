#!/usr/bin/env bash
# Checks an environment on its domain: the API and its database report ok, and the app's
# HTML is served. Retries for up to 5 minutes, since a fresh deploy can take a moment to
# become reachable. Then checks that the distribution's own d….cloudfront.net name
# redirects to the domain, for the app's paths and the API's.
#
#   infra/scripts/smoke-test.sh staging|prod

# shellcheck source=lib.sh
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

require_environment "${1:-}"
url="https://$(tf_output domain)"
cloudfront_url="https://$(tf_output cloudfront_domain)"

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

for path in "/orders?smoke=a%20b" "/api/health/?smoke=a%20b"; do
  redirect=$(curl -sS --max-time 10 --retry 2 -o /dev/null -w '%{http_code} %{redirect_url}' "$cloudfront_url$path")
  [ "$redirect" = "301 $url$path" ] ||
    die "$cloudfront_url$path should redirect to $url$path with a 301, got: $redirect"
done
log "$cloudfront_url redirects to $url"

log "Smoke test passed: $url"
