# The MCP portal's upstream servers.
#
# What matters here is `scope`: the portal is its own OAuth client against each
# upstream, and it only ever receives the scopes it names. mctl-telegram's
# narrowGrant (internal/oauth/scopes.go) drops any negotiable scope the client
# did not ask for, so a short string here is invisible everywhere else —
# measured on 2026-09-12, with all 30 tools enabled, the identity on the admin
# tier and per-account send consent on, a send still came back as a dry-run
# preview because the portal was asking for two read scopes:
#
#   oauth: token authorization_code grant
#   client_id:       cloudflare-portal-mcp
#   requested_scope: telegram:dialogs:read telegram:messages:read
#   granted_scope:   telegram:dialogs:read telegram:messages:read admin:users
#
# (`admin:users` survives only because it is not negotiable and is granted by
# membership. Its presence next to a missing send scope is the signature of
# this failure: the tier was never the problem.)
#
# Applying a wider scope does not widen a live session. mctl-telegram's
# boundRefreshGrant intersects a refresh with the family's original grant, so
# after an apply the upstream must be signed out and back in in the portal.

locals {
  # The five scopes tg.mctl.ai advertises in its RFC 8414 and RFC 9728
  # metadata, which is also exactly DCRNegotiableScopes in
  # mctl-telegram/internal/oauth/scopes.go. A direct connector to tg.mctl.ai
  # asks for and receives all five; the portal is brought level with it.
  tg_scope = join(" ", [
    "telegram:dialogs:read",
    "telegram:messages:read",
    "telegram:messages:send",
    "telegram:messages:pin",
    "account:manage",
  ])
}

# Adopting what is already live rather than creating it: the server was made
# through the dashboard on 2026-09-10. Measured before this landed — the import
# plans one update and nothing else, `client_secret` does not appear in the
# diff at all, and there is no replacement.
import {
  to = cloudflare_zero_trust_access_ai_controls_mcp_server.tg
  id = "${var.account_id}/tg"
}

resource "cloudflare_zero_trust_access_ai_controls_mcp_server" "tg" {
  account_id = var.account_id
  id         = "tg"
  name       = "mctl Telegram (tg.mctl.ai)"
  hostname   = "https://tg.mctl.ai/mcp"
  auth_type  = "oauth"

  description = "Phase 0 pilot upstream for the private aggregate portal. Refs mctlhq/.github#35, #44."

  secure_web_gateway               = false
  is_shared_oauth_callback_enabled = false

  # The OAuth registration the portal uses against this upstream. The API
  # takes it as one opaque write-only blob and never returns it; only the
  # read-only auth_config_summary projection comes back, which is why a
  # refresh cannot correct this value and why the drift of it is checked
  # separately (scripts/portal-auth-credentials-drift.py).
  #
  # `client_secret` is deliberately absent. It is a separate top-level field,
  # not part of this blob, and the stored one (v1) must survive an apply:
  # naming it here would mean committing a secret to state for no gain. Note
  # the asymmetry, measured: CREATING a manual-mode oauth server requires a
  # non-empty client_secret (the API answers `7001: client_secret must be a
  # non-empty string`), while updating one does not. A future server added
  # here from scratch will have to supply one; adopting this one does not.
  auth_credentials = jsonencode({
    auth_mode = "manual"
    config = {
      issuer                 = "https://tg.mctl.ai"
      authorization_endpoint = "https://tg.mctl.ai/oauth/authorize"
      token_endpoint         = "https://tg.mctl.ai/oauth/token"
      revocation_endpoint    = "https://tg.mctl.ai/oauth/revoke"
    }
    registration_info = {
      client_id                  = "cloudflare-portal-mcp"
      redirect_uris              = ["https://mcp.mctl.ai/servers-callback"]
      token_endpoint_auth_method = "none"
      scope                      = local.tg_scope
    }
  })

  lifecycle {
    # `tools` and `prompts` are the capability catalogue Cloudflare syncs from
    # the upstream, and `updated_tools` / `updated_prompts` are the allowlists
    # owned by mctl-telegram, mctl-api and seerrsense — applied from those
    # repositories, and deliberately not described here. Nothing in this file
    # sets them, so nothing in this file can revert them.
    ignore_changes = [updated_tools, updated_prompts]
  }
}
