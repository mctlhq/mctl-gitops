# Cloudflare Web Analytics for mctl.ai
#
# Enables lightweight, cookieless RUM analytics with automatic beacon injection
# for all proxied hostnames in the zone (*.mctl.ai).

resource "cloudflare_web_analytics_site" "mctl_ai" {
  account_id   = "6a09f637d20e1f66a8e9d45ebe778058"
  zone_tag     = local.zone_id
  auto_install = true
  enabled      = true
}
