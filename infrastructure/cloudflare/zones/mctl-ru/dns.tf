# DNS records for mctl.ru.
#
# Derived from `tofu plan -generate-config-out`, then reduced: the generator
# emits every optional attribute as an explicit null, which is noise rather
# than intent. Only attributes that carry real configuration are kept — the
# zero-diff plan is what proves the reduction is safe.

locals {
  # Shared origin for the platform zones. Every tenant host resolves through
  # the wildcard below.
  origin_ip = "91.98.10.188"
}

resource "cloudflare_dns_record" "apex" {
  zone_id = local.zone_id
  name    = "mctl.ru"
  type    = "A"
  content = local.origin_ip
  proxied = true
  ttl     = 1 # 1 = automatic
}

resource "cloudflare_dns_record" "wildcard" {
  zone_id = local.zone_id
  name    = "*.mctl.ru"
  type    = "A"
  content = local.origin_ip
  proxied = true
  ttl     = 1
}

# Deliberately NOT managed here: TXT _acme-challenge.mctl.ru
#
# The value is a DNS-01 challenge digest rotated by the certificate issuer.
# Pinning it in Git would mean a later write-capable apply could restore a
# stale digest over a live challenge and break certificate renewal.
#
# An earlier revision imported it "so that a plan does not propose deleting
# it". That reasoning was wrong: OpenTofu only destroys resources it tracks,
# so a record absent from this configuration is simply left alone.
