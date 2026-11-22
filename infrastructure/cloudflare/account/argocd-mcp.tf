# argocd.mctl.ai — a read-only Argo CD MCP server, reached through the MCP portal
# at mcp.mctl.ai. It is the seventh upstream and the same shape as projects.mctl.ai
# (projects-mcp.tf): Cloudflare Access is the OAuth authorization server for the
# application and the origin only verifies the `Cf-Access-Jwt-Assertion` it
# forwards, against https://mbank.cloudflareaccess.com/cdn-cgi/access/certs with
# this application's `aud`.
#
# Unlike projects it is an ADMIN surface, so the differences are deliberate:
#   - ZITADEL only. No Google, no one-time PIN. ZITADEL hands Access a token only to
#     holders of the project role `access` (see portal-zitadel.tf), which is the
#     platform admins. The reusable zitadel_access_role policy is reused as is.
#   - The only OAuth clients allowed to register are the portal and the Cloudflare
#     dashboard (which completes the first upstream login). No claude.ai, ChatGPT or
#     loopback clients: nobody is meant to add this as a direct connector.
#
# Terraform cannot do the next step. After the apply an admin completes the
# upstream OAuth login once from the dashboard ("Authenticate server"); the server
# sits in `waiting` until then (infrastructure/cloudflare/portal/mcp-servers.tf).
resource "cloudflare_zero_trust_access_application" "argocd_mcp" {
  account_id = var.account_id
  name       = "Argo CD MCP (argocd.mctl.ai)"
  type       = "self_hosted"

  domain = "argocd.mctl.ai"
  destinations = [
    {
      type = "public"
      uri  = "argocd.mctl.ai"
    },
  ]

  # No DNS record is needed: `A *.mctl.ai` is proxied and already resolves this host
  # to the cluster origin (zones/mctl-ai/dns.tf), which is what puts Access in front.
  allowed_idps = [
    cloudflare_zero_trust_access_identity_provider.zitadel.id,
  ]

  auto_redirect_to_identity = false
  app_launcher_visible      = false
  session_duration          = "8760h"

  oauth_configuration = {
    enabled = true
    dynamic_client_registration = {
      enabled = true
      allowed_uris = [
        "https://mcp.mctl.ai/servers-callback",
        "https://dash.cloudflare.com/${var.account_id}/one/access-controls/ai-controls/mcp-server/oauth-callback/argocd",
      ]
      allow_any_on_loopback  = false
      allow_any_on_localhost = false
    }
    grant = {
      access_token_lifetime = "1h"
      session_duration      = "8760h"
    }
  }

  policies = [
    {
      id         = cloudflare_zero_trust_access_policy.zitadel_access_role.id
      precedence = 1
    },
  ]
}

output "argocd_mcp_aud" {
  description = "MCP_AUTH_AUDIENCE for argocd-mcp (platform-gitops/services/labs/argocd-mcp/values.yaml)."
  value       = cloudflare_zero_trust_access_application.argocd_mcp.aud
}
