#!/usr/bin/env bash
# Uploads a frontend build to the environment's bucket and invalidates CloudFront's
# cache. Vite's hashed files under assets/ never change, so browsers may keep them for a
# year; everything else, index.html above all, must be revalidated on every visit.
#
#   infra/scripts/publish-frontend.sh staging|prod <dist directory>

# shellcheck source=lib.sh
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

require_environment "${1:-}" "<dist directory>"
dist=${2:-}
[ -f "$dist/index.html" ] || die "${dist:-<dist directory>} isn't a frontend build: no index.html"

bucket=$(tf_output frontend_bucket)
distribution=$(tf_output cloudfront_distribution_id)

# Assets first, so the new index.html never refers to files that aren't there yet.
log "Uploading $dist to s3://$bucket"
aws s3 sync "$dist/assets" "s3://$bucket/assets" --only-show-errors \
  --cache-control "public, max-age=31536000, immutable"
aws s3 sync "$dist" "s3://$bucket" --only-show-errors --exclude "assets/*" \
  --cache-control "no-cache"
log "Removing files the build no longer has"
aws s3 sync "$dist" "s3://$bucket" --only-show-errors --delete

invalidation=$(aws cloudfront create-invalidation --distribution-id "$distribution" --paths '/*' \
  --query 'Invalidation.Id' --output text)
log "Waiting for CloudFront invalidation $invalidation"
aws cloudfront wait invalidation-completed --distribution-id "$distribution" --id "$invalidation"
log "Frontend published"
