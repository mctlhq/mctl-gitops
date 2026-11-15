# glovo.mctl.ai served from the operator's Mac mini (mctlhq/mctl-glovo,
# cmd/glovo-home), instead of the in-cluster mctl-api host.
#
#   MCP client -> Cloudflare (glovo.mctl.ai, proxied CNAME to this tunnel)
#              -> tunnel glovo-home (cloudflared LaunchAgent on the Mac mini,
#                 outbound-only, `tunnel run --token-file`)
#              -> http://127.0.0.1:8787 on the Mac mini (glovo-home)
#
# No Access application: the endpoint is a public OAuth-protected MCP
# resource, like it is today on mctl-api. glovo-home itself answers 401 with
# RFC 9728 metadata and verifies every bearer token (EdDSA against the
# api.mctl.ai JWKS, exact iss and aud, principal allowlist).
#
# Nothing is routed by this file alone. The CNAME that moves glovo.mctl.ai
# off the wildcard A to this tunnel lands in ../zones/mctl-ai/dns.tf in a
# separate change, after the connector is up and checked; reverting that
# CNAME is the rollback.
#
# Secrets stay out of this state, as for events-tunnel.tf: the tunnel is
# created without `tunnel_secret`, so Cloudflare generates it. The connector
# token is read once from the dashboard (Networks > Tunnels > glovo-home)
# into Vault secret/platform/glovo-home-tunnel, property tunnel-token, and
# from there into a 0600 token file on the Mac mini only.

resource "cloudflare_zero_trust_tunnel_cloudflared" "glovo_home" {
  account_id = var.account_id
  name       = "glovo-home"
  config_src = "cloudflare"
}

resource "cloudflare_zero_trust_tunnel_cloudflared_config" "glovo_home" {
  account_id = var.account_id
  tunnel_id  = cloudflare_zero_trust_tunnel_cloudflared.glovo_home.id

  config = {
    ingress = [
      {
        hostname = "glovo.mctl.ai"
        # glovo-home accepts only this Host (and loopback names) and answers
        # 421 otherwise, so the header is pinned rather than left to the
        # connector's default.
        service = "http://127.0.0.1:8787"
        origin_request = {
          http_host_header = "glovo.mctl.ai"
        }
      },
      # Required catch-all: any other hostname routed to this tunnel by
      # mistake gets a 404 instead of reaching the Mac mini.
      {
        service = "http_status:404"
      },
    ]
  }
}

output "glovo_home_tunnel_id" {
  description = "Tunnel id for the glovo CNAME in ../zones/mctl-ai/dns.tf."
  value       = cloudflare_zero_trust_tunnel_cloudflared.glovo_home.id
}
