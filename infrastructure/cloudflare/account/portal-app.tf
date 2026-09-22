# The Access application of the MCP portal itself (type `mcp_portal`,
# mcp.mctl.ai) -- the door every Claude connector to the portal goes through.
#
# Created by the dashboard with the portal on 2026-09-10 and unmanaged until
# now. It is adopted here for one field: `session_duration`. The portal runs
# its own OAuth server (https://mcp.mctl.ai/token, not Access's managed
# OAuth -- this application has no `oauth_configuration`), and the grant it
# hands a connector lasted as long as this session: 24h, the dashboard
# default. So the whole gateway asked to sign in again roughly once a day
# (Access logs: logins to mcp.mctl.ai at 2026-09-21 21:39 and 22:45,
# 2026-09-22 08:19 and 23:00).
#
# 8760h is one year, chosen deliberately by the owner. Cloudflare documents
# one month as the ceiling for an application session, but the API does not
# validate it (a probe app accepted up to 87600h on 2026-09-23 and read it
# back unchanged); should Access clamp it at runtime, the month still applies.
#
# Every other field is copied from the live application
# (GET /accounts/{account_id}/access/apps/fd76d449-63a4-4c3a-83c5-4686a3815d2c)
# so that the import plans as an in-place change of `session_duration` alone.
# `oauth_configuration` is deliberately left unset: turning on Access managed
# OAuth here would replace the portal's authorization server under every
# connected client.
import {
  to = cloudflare_zero_trust_access_application.mcp_portal
  id = "accounts/6a09f637d20e1f66a8e9d45ebe778058/fd76d449-63a4-4c3a-83c5-4686a3815d2c"
}

resource "cloudflare_zero_trust_access_application" "mcp_portal" {
  account_id = var.account_id
  name       = "mctl private aggregate (mcp.mctl.ai)"
  type       = "mcp_portal"
  domain     = "mcp.mctl.ai"

  destinations = [
    {
      type = "public"
      uri  = "mcp.mctl.ai"
    },
  ]

  allowed_idps              = []
  auto_redirect_to_identity = false

  cors_headers = {
    allow_all_headers = true
    allow_all_methods = true
    allow_all_origins = true
  }

  session_duration = "8760h"

  policies = [
    {
      name       = "Phase 0 pilot users"
      decision   = "allow"
      precedence = 1

      include = [
        { email = { email = "mashkoffdmitry@gmail.com" } },
        { email = { email = "mashkovdm.dm@gmail.com" } },
      ]
    },
  ]
}
