# DNS records for mctl.ru.
#
# Derived from `tofu plan -generate-config-out`, then reduced: the generator
# emits every optional attribute as an explicit null, which is noise rather
# than intent. Only attributes that carry real configuration are kept — the
# zero-diff plan below is what proves the reduction is safe.

resource "cloudflare_dns_record" "apex" {
  zone_id = local.zone_id
  name    = "mctl.ru"
  type    = "A"
  content = "91.98.10.188"
  proxied = true
  ttl     = 1 # 1 = automatic
}

resource "cloudflare_dns_record" "wildcard" {
  zone_id = local.zone_id
  name    = "*.mctl.ru"
  type    = "A"
  content = "91.98.10.188"
  proxied = true
  ttl     = 1
}

# Persistent DNS-01 challenge record. Owned by whoever issues the certificate,
# not by this module — it is imported so that a plan does not propose deleting
# it, not so that it can be edited from here.
resource "cloudflare_dns_record" "acme_challenge" {
  zone_id = local.zone_id
  name    = "_acme-challenge.mctl.ru"
  type    = "TXT"
  content = "\"Biv-kFtFBP9wPP9FHGbbfV7btEWYpmsxR-JyX0_VOeY\""
  proxied = false
  ttl     = 1
}
