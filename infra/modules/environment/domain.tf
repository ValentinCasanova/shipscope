# The environment's own domain, in the hosted zone from infra/bootstrap: prod on its apex,
# staging on a subdomain. Google sends sign-ins back only to redirect URLs registered in
# advance, and unlike the distribution's d….cloudfront.net name, the domain stays the
# same when parking staging recreates the distribution.

data "aws_route53_zone" "main" {
  name = var.hosted_zone
}

# CloudFront only uses certificates from us-east-1, whatever the Region of the rest of
# the stack. ACM renews the certificate on its own while the validation record exists.
resource "aws_acm_certificate" "main" {
  region            = "us-east-1"
  domain_name       = var.domain
  validation_method = "DNS"

  # A replacement must exist before the distribution can switch to it, and ACM refuses
  # to delete a certificate that's still in use.
  lifecycle {
    create_before_destroy = true
  }
}

# The record proves to ACM that this account controls the domain. ACM asks for the same
# record for every certificate for a domain in one account, so after an interrupted
# apply the record may already exist; allow_overwrite adopts it.
resource "aws_route53_record" "certificate_validation" {
  for_each = {
    for option in aws_acm_certificate.main.domain_validation_options : option.domain_name => option
  }

  zone_id         = data.aws_route53_zone.main.zone_id
  name            = each.value.resource_record_name
  type            = each.value.resource_record_type
  records         = [each.value.resource_record_value]
  ttl             = 300
  allow_overwrite = true
}

# Waits until ACM has issued the certificate, usually a few minutes after the record
# appears. The distribution takes the certificate's ARN from here, so it never gets a
# certificate that isn't issued yet.
resource "aws_acm_certificate_validation" "main" {
  region                  = "us-east-1"
  certificate_arn         = aws_acm_certificate.main.arn
  validation_record_fqdns = [for record in aws_route53_record.certificate_validation : record.fqdn]
}

# The domain points at the distribution. Alias records answer with CloudFront's current
# IPv4 and IPv6 addresses, and Route 53 doesn't charge for queries to them. They're
# created only after the distribution accepts the domain.
resource "aws_route53_record" "alias" {
  for_each = toset(["A", "AAAA"])

  zone_id = data.aws_route53_zone.main.zone_id
  name    = var.domain
  type    = each.key

  alias {
    name                   = aws_cloudfront_distribution.main.domain_name
    zone_id                = aws_cloudfront_distribution.main.hosted_zone_id
    evaluate_target_health = false
  }
}
