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
    # the upstream. `updated_tools` / `updated_prompts` are written by the
    # portal resource in mcp-portal.tf, built from the owning repo's
    # allowlist vendored under allowlists/ (#1370). Declaring them here too
    # would give this root two writers of one mapping, so they stay ignored.
    ignore_changes = [updated_tools, updated_prompts]
  }
}

# The fourth upstream, and the first registered by dynamic client registration
# rather than by hand.
#
# `tg` above is the only `auth_mode: manual` resource in this file today. It
# stays manual until mctl-telegram conforms to the automatic (DCR)
# registration rule in mctlhq/.github#137 — its DCR default drops any scope
# the client did not name, which would silently narrow what the portal is
# granted. `api` is also live in manual mode, with no Terraform resource yet
# (issue mctlhq/mctl-gitops#1363, blocked on mctlhq/mctl-api#395); `seerrsense`
# moved to DCR on 2026-09-25 and is adopted at the end of this file. Manual
# mode costs a server the thing this one is being registered to test: a manual server's capability catalogue is captured
# once, at the first user authorization, and never refreshed. That is
# Cloudflare's documented limitation, and it is why `POST servers/{id}/sync`
# answers `success` on a manual server while `last_synced` does not move —
# synchronisation runs with an admin credential that only DCR registration
# has.
#
# `projects.mctl.ai` can have that credential. It sits behind a Cloudflare
# Access application with Managed OAuth and DCR enabled, so the portal can
# register itself as a client without anybody pasting a client_id: hence no
# `auth_credentials` and no `client_secret` here at all. Supplying either is
# what opts a server INTO manual mode, which is the mode we are trying not to
# be in.
#
# What Terraform cannot do is the next step. After the apply, an admin opens
# the server in the dashboard and completes the upstream OAuth login once;
# that account becomes the admin credential used for every later sync. Until
# then the server sits in `waiting`. Two consequences worth knowing before
# that login:
#
#   - Whoever logs in decides what the snapshot contains. This server hands an
#     admin caller two more tools than a customer, so the snapshot taken by an
#     owner address carries all eight. That is deliberate and is the decision
#     recorded in mctlhq/projects-mcp docs/portal-allowlist.json.
#   - The admin credential expires on the upstream's schedule and nobody is
#     notified. `authentication_status` goes `stale` and the server stops
#     appearing for end users. It is a read-only attribute, so it is worth
#     watching rather than discovering.
#
# Customers do not reach this server through the portal and never will: they
# add https://projects.mctl.ai/mcp as a connector directly, where Access is
# the OAuth provider. The portal is the owner's own aggregate view.
resource "cloudflare_zero_trust_access_ai_controls_mcp_server" "projects" {
  account_id = var.account_id
  id         = "projects"
  name       = "mctl Projects (projects.mctl.ai)"
  hostname   = "https://projects.mctl.ai/mcp"
  auth_type  = "oauth"

  description = "Customer-facing documentation and live status, per project, filtered by a per-address grant. Registered by DCR to test whether capability sync works where manual registration cannot. Refs mctlhq/.github#35, #64."

  secure_web_gateway               = false
  is_shared_oauth_callback_enabled = false

  lifecycle {
    # Same reasoning as tg above: mcp-portal.tf writes the mapping, from
    # allowlists/projects.json (vendored from mctlhq/projects-mcp).
    ignore_changes = [updated_tools, updated_prompts]
  }
}

# The fifth upstream, and the second registered by DCR rather than by hand —
# but for a different reason than `projects`. `alice.mctl.ai` is not fronted
# by Cloudflare Access at all; the service IS its own OAuth authorization
# server (src/auth/oauth-controller.ts in mctlhq/mctl-alice), with a fully
# open `POST /oauth/register` that accepts any client and
# `token_endpoint_auth_methods_supported` including "none". Measured directly
# before writing this: a probe registration against
# https://alice.mctl.ai/oauth/register with this portal's own callback,
# https://mcp.mctl.ai/servers-callback, as `redirect_uris` succeeds and
# returns a client_id/client_secret pair — so, same as `projects`, no
# `auth_credentials` and no `client_secret` here: supplying either is what
# opts a server INTO manual mode, which this server does not need.
#
# What Terraform still cannot do is the first sync. The server sits in
# `waiting` until an admin completes the upstream OAuth login once from the
# dashboard; only then does its tool catalogue populate, and only then can
# mcp-portal.tf map it on the portal. Whoever logs in decides what the twelve
# tools in the
# snapshot are: alice_list_devices, alice_send_command,
# alice_say_phrase, alice_set_volume, alice_media_control,
# alice_trigger_scenario, alice_control_device, alice_get_device_state,
# alice_get_device_history, alice_set_light, alice_control_room,
# alice_get_home_summary (mctlhq/mctl-alice src/tools/definitions.ts). Which
# of them are exposed is mctl-alice's docs/portal-allowlist.json, vendored as
# allowlists/alice.json.
resource "cloudflare_zero_trust_access_ai_controls_mcp_server" "alice" {
  account_id = var.account_id
  id         = "alice"
  name       = "Yandex Alice Smart Home (alice.mctl.ai)"
  hostname   = "https://alice.mctl.ai/mcp"
  auth_type  = "oauth"

  description = "Yandex Alice smart-home control (devices, scenarios, rooms). Registered by DCR: the upstream is its own authorization server, not fronted by Access. Refs mctlhq/.github#35."

  secure_web_gateway               = false
  is_shared_oauth_callback_enabled = false

  lifecycle {
    # Same reasoning as tg above: mcp-portal.tf writes the mapping, from
    # allowlists/alice.json (vendored from mctlhq/mctl-alice).
    ignore_changes = [updated_tools, updated_prompts]
  }
}

# The sixth upstream, and a new member rather than an adoption: `coolify` is
# not on the portal at all today. `coolify.mctl.ai` offers CIMD with a DCR
# fallback and grants its `coolify` scope when no scope is named, so this is
# registered the same way as `projects`/`alice` — `auth_type = "oauth"`, no
# `auth_credentials`, no `client_secret` — which also sidesteps the
# `client_secret` requirement, since that only applies to manual-mode
# creates. Refs mctlhq/mctl-gitops#1363, mctlhq/.github#137.
#
# The apply leaves it in `waiting`. An admin then completes the upstream OAuth
# login once from the dashboard, from the owner address to match the
# `projects`/`alice` precedent, and that account becomes the admin credential
# for every later sync. Only then does it have a catalogue for mcp-portal.tf
# to map. Coolify's destructive tools (`stop_all_apps`, deletes, bulk env
# updates) are reachable through the upstream but not exposed here: which
# tools go live is a separate decision, recorded in a
# `docs/portal-allowlist.json` in `mctlhq/mctl-coolify-mcp` and vendored as
# allowlists/coolify.json, same split as every other member.
resource "cloudflare_zero_trust_access_ai_controls_mcp_server" "coolify" {
  account_id = var.account_id
  id         = "coolify"
  name       = "Coolify (coolify.mctl.ai)"
  hostname   = "https://coolify.mctl.ai/mcp"
  auth_type  = "oauth"

  description = "Coolify deployment platform control, read-mostly by default. Registered by DCR: the upstream offers CIMD with a DCR fallback. Refs mctlhq/mctl-gitops#1363, mctlhq/.github#35, #137."

  secure_web_gateway               = false
  is_shared_oauth_callback_enabled = false

  lifecycle {
    # Same reasoning as tg above: mcp-portal.tf writes the mapping, from
    # allowlists/coolify.json (vendored from mctlhq/mctl-coolify-mcp).
    ignore_changes = [updated_tools, updated_prompts]
  }
}

# The seventh resource, and an adoption: `seerrsense` was created by hand in
# the dashboard on 2026-09-10 in manual mode, and moved to automatic (DCR)
# mode on 2026-09-25 (mctlhq/mctl-gitops#1363). The move was done against the
# API, not by Terraform, because the provider cannot express it:
# `auth_credentials` is write-only, so leaving it out of a resource never
# clears a manual registration that already exists. The measured sequence:
#
#   1. PUT {auth_type: "bearer", auth_credentials: "<dummy>"}, which clears the
#      stored manual registration (auth_config_summary becomes null);
#   2. PUT {auth_type: "oauth", name, description}, with no auth_credentials.
#      A PUT carrying auth_type alone answers 7000 "D1_ERROR: near WHERE";
#      with name and description it succeeds, and the dashboard then shows
#      the server as "Automatic (recommended)";
#   3. "Authenticate server" in the dashboard. Cloudflare registers itself
#      at https://seerrsense.mctl.ai/register, which admits only the two
#      portal callbacks in SEERRSENSE_DCR_REDIRECT_URIS (mctlhq/seerrsense#74),
#      and the owner address signs in and consents.
#
# Afterwards: status ready, authentication_status connected, last_synced
# moved from 2026-09-13 to 2026-09-25 23:13 on its own, and the portal
# mapping (five tools, all enabled) survived untouched. From here the
# catalogue is synced by Cloudflare, so a new seerrsense tool reaches the
# portal without a re-snapshot.
#
# No auth_credentials and no client_secret, as for projects/alice/coolify:
# supplying either is what opts a server INTO manual mode.
import {
  to = cloudflare_zero_trust_access_ai_controls_mcp_server.seerrsense
  id = "${var.account_id}/seerrsense"
}

resource "cloudflare_zero_trust_access_ai_controls_mcp_server" "seerrsense" {
  account_id = var.account_id
  id         = "seerrsense"
  name       = "seerrsense (seerrsense.mctl.ai)"
  hostname   = "https://seerrsense.mctl.ai/mcp"
  auth_type  = "oauth"

  description = "Second upstream of the private aggregate portal. Registered by DCR (portal-restricted, mctlhq/seerrsense#74). Refs mctlhq/.github#35, #137, mctlhq/mctl-gitops#1363."

  secure_web_gateway               = false
  is_shared_oauth_callback_enabled = false

  lifecycle {
    # Same reasoning as tg above: mcp-portal.tf writes the mapping, from
    # allowlists/seerrsense.json (vendored from mctlhq/seerrsense).
    ignore_changes = [updated_tools, updated_prompts]
  }
}
