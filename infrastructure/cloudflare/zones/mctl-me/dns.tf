# Records specific to mctl.me. The apex and wildcard are in the shared
# baseline module; these are the ones mctl.ru has no equivalent of.
#
# Derived from `tofu plan -generate-config-out`, then reduced — the generator
# emits every optional attribute as an explicit null. The zero-diff plan is
# what proves the reduction safe.

resource "cloudflare_dns_record" "www" {
  zone_id = local.zone_id
  name    = "www.mctl.me"
  type    = "A"
  content = local.origin_ip
  proxied = true
  ttl     = 1 # 1 = automatic
}

resource "cloudflare_dns_record" "platform" {
  zone_id = local.zone_id
  name    = "platform.mctl.me"
  type    = "A"
  content = local.origin_ip
  proxied = true
  ttl     = 1
}

# --- Mail: Amazon SES for sending, Resend for DKIM ---

resource "cloudflare_dns_record" "send_mx" {
  zone_id  = local.zone_id
  name     = "send.mctl.me"
  type     = "MX"
  content  = "feedback-smtp.eu-west-1.amazonses.com"
  priority = 10
  proxied  = false
  ttl      = 3600
}

resource "cloudflare_dns_record" "send_spf" {
  zone_id = local.zone_id
  name    = "send.mctl.me"
  type    = "TXT"
  content = "\"v=spf1 include:amazonses.com ~all\""
  proxied = false
  ttl     = 3600
}

resource "cloudflare_dns_record" "resend_dkim" {
  zone_id = local.zone_id
  name    = "resend._domainkey.mctl.me"
  type    = "TXT"
  content = "\"p=MIGfMA0GCSqGSIb3DQEBAQUAA4GNADCBiQKBgQCd7PJBffJZsy4AKd+ZPToQPb/obB2VJvDkr7xWteZZr/1Gh+bkJK/p8l+oD0WBrOMVHEX7ojrD2gx3U7GBhrMBYsOz8uixZPp/Z41+6yyd6CIjC1mF0hfd5ty/IUs+mS4MYPi9wZiof98MCvldBaoOKZI7ahePqlb5QhmF2l9gLwIDAQAB\""
  proxied = false
  ttl     = 3600
}

resource "cloudflare_dns_record" "dmarc" {
  zone_id = local.zone_id
  name    = "_dmarc.mctl.me"
  type    = "TXT"
  content = "\"v=DMARC1; p=none;\""
  proxied = false
  ttl     = 1
}

# Domain-verification token for a third party. Kept in Git because it is a
# static proof of ownership, unlike an ACME challenge digest, which rotates and
# is deliberately left unmanaged on mctl.ru.
resource "cloudflare_dns_record" "tbolt" {
  zone_id = local.zone_id
  name    = "tbolt.mctl.me"
  type    = "TXT"
  content = "\"d93a329e-1555-49b8-b742-03b06dd22c6a\""
  proxied = false
  ttl     = 1
}
