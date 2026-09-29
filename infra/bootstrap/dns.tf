# The domain's public hosted zone. Route 53 created it when the domain was registered,
# and the registration delegates the domain to its name servers. Each environment stack
# adds its own records: its certificate's validation record, and the alias records that
# point its domain at its CloudFront distribution.
#
# Deleting the zone would take both environments offline, and a new zone gets new name
# servers, which the registration would then have to list. So Terraform refuses to
# destroy it.

resource "aws_route53_zone" "main" {
  name = var.domain
  # The comment Route 53 gave the zone, kept so that adopting the zone changed nothing.
  comment = "HostedZone created by Route53 Registrar"

  lifecycle {
    prevent_destroy = true
  }
}
