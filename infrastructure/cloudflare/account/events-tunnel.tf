# events-valkey.mctl.ai — the platform event bus (Valkey Streams in
# platform-events, mctlhq/.github#87) reached from outside the cluster by one
# consumer: the operator's own Claude Code session on the home Mac mini, which
# replaces the paused labs/claude-remote pod as the Channel host.
#
#   Mac mini: cloudflared access tcp --hostname events-valkey.mctl.ai
#             --url 127.0.0.1:6379 (+ service token)
#        -> Cloudflare Access: this application, service token only
#        -> tunnel mctl-platform-events (cloudflared Deployment in
#           platform-events, outbound-only)
#        -> tcp://valkey.platform-events.svc.cluster.local:6379
#
# Nothing in the cluster listens publicly. Access is the only gate in front of
# the hostname, and Valkey's own ACL (the claude-remote user, see
# platform-gitops/infra-components/data/valkey/externalsecret.yaml) still
# bounds what an authenticated connection can do.
#
# Secrets stay out of this state:
# - the tunnel is created here without `tunnel_secret`, so Cloudflare generates
#   it and the plan never sees it. The connector token is read once from the
#   dashboard (Networks > Tunnels > mctl-platform-events > Configure) into
#   Vault secret/platform/events-tunnel, property tunnel-token;
# - the service token is created by hand and only referenced by id, the same
#   way seerrsense's is (access-legacy-apps.tf): a managed token would carry its
#   client secret in state. Its id and secret live in Vault
#   secret/platform/events-tunnel (service-token-client-id/-secret) and on the
#   Mac mini only.
#
# The proxied CNAME events-valkey.mctl.ai -> <tunnel id>.cfargotunnel.com lives
# in ../zones/mctl-ai/dns.tf; this root's token has no DNS permission.

# Ids are literal for the reason given in portal-mcp-apps-adopted.tf. The
# token id is not a secret; it names an object in this account.
locals {
  events_tunnel_service_token_id = "adb42a29-cdb4-412d-92dc-39cb4792b8b1" # mac-mini-events, expires 2027-10-29
}

resource "cloudflare_zero_trust_tunnel_cloudflared" "platform_events" {
  account_id = var.account_id
  name       = "mctl-platform-events"
  config_src = "cloudflare"
}

resource "cloudflare_zero_trust_tunnel_cloudflared_config" "platform_events" {
  account_id = var.account_id
  tunnel_id  = cloudflare_zero_trust_tunnel_cloudflared.platform_events.id

  config = {
    ingress = [
      {
        hostname = "events-valkey.mctl.ai"
        service  = "tcp://valkey.platform-events.svc.cluster.local:6379"
      },
      # Required catch-all: any other hostname routed to this tunnel by mistake
      # gets a 404 instead of reaching Valkey.
      {
        service = "http_status:404"
      },
    ]
  }
}

resource "cloudflare_zero_trust_access_policy" "events_valkey_service_token" {
  account_id = var.account_id
  name       = "events-valkey service token"
  decision   = "non_identity"

  include = [
    { service_token = { token_id = local.events_tunnel_service_token_id } },
  ]
}

resource "cloudflare_zero_trust_access_application" "events_valkey" {
  account_id = var.account_id
  name       = "events-valkey (platform event bus, Mac mini consumer)"
  type       = "self_hosted"
  domain     = "events-valkey.mctl.ai"

  destinations = [
    {
      type = "public"
      uri  = "events-valkey.mctl.ai"
    },
  ]

  # No identity provider and no launcher tile: the only way in is the service
  # token policy below. A human browser hitting the hostname gets a denial.
  allowed_idps         = []
  app_launcher_visible = false
  session_duration     = "24h"

  policies = [
    { id = cloudflare_zero_trust_access_policy.events_valkey_service_token.id, precedence = 1 },
  ]
}

output "events_tunnel_id" {
  description = "Tunnel id for the events-valkey CNAME in ../zones/mctl-ai/dns.tf."
  value       = cloudflare_zero_trust_tunnel_cloudflared.platform_events.id
}
