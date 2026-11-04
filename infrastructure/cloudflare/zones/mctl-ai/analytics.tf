# Cloudflare Web Analytics for mctl.ai
#
# Enables lightweight, cookieless RUM analytics with automatic beacon injection
# for all proxied hostnames in the zone (*.mctl.ai).

resource "cloudflare_web_analytics_site" "mctl_ai" {
  account_id   = local.account_id
  zone_tag     = local.zone_id
  auto_install = true
  enabled      = true
}
