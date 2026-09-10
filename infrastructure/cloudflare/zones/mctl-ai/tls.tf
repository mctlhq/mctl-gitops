# Edge TLS policy for mctl.ai.
#
# mctl.me and mctl.ru get these from modules/zone-baseline; mctl.ai does not
# use that module — it serves traffic rather than redirecting, so it is a flat
# root — and therefore declares the same two settings itself. The values are
# deliberately identical; see the module for the reasoning behind each, and for
# why they were applied through the API before being declared here.
#
# min_tls_version was "1.0" here too. mctl.ai carries the overwhelming majority
# of the account's traffic — 750 757 requests over 2026-09-03..09 — and of the
# 736 995 that arrived over TLS, 732 284 were TLS 1.3 and 4 711 were TLS 1.2.
# Zero TLS 1.0, zero TLS 1.1. Raising the floor to 1.2 refuses nothing.
#
# always_use_https was "off", and unlike the redirect zones mctl.ai actually
# serves content, so the 13 762 plaintext requests in that week were answered
# over :80 rather than redirected. Automatic HTTPS Rewrites is on, but that
# only rewrites subresource URLs inside HTML — it does nothing for the first
# request.
#
# ssl stays "full" for the reason recorded in #1153: the origin presents
# TRAEFIK DEFAULT CERT for every name except this zone's apex, so "strict"
# would answer 526 for www.mctl.ai and every tenant subdomain under the
# wildcard.
resource "cloudflare_zone_setting" "min_tls_version" {
  zone_id    = local.zone_id
  setting_id = "min_tls_version"
  value      = "1.2"
}

resource "cloudflare_zone_setting" "always_use_https" {
  zone_id    = local.zone_id
  setting_id = "always_use_https"
  value      = "on"
}
