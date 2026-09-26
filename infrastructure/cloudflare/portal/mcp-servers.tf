# The MCP portal's upstream servers.
#
# Every server here is registered by dynamic client registration (DCR, the
# dashboard's "Automatic (recommended)"): `auth_type = "oauth"` with no
# `auth_credentials` and no `client_secret`. Supplying either is what opts a
# server INTO manual mode, whose tool catalogue is captured once at the first
# login and never refreshed. `tg` and `api` were the last two manual servers;
# both moved on 2026-09-26 (mctlhq/mctl-gitops#1363), see the end of this
# file.
#
# Scope was the reason `tg` carried a hand-written registration: the portal
# only receives the scopes it names, and mctl-telegram's narrowGrant drops any
# negotiable scope the client did not ask for -- measured 2026-09-12, a send
# came back as a dry-run preview because the manual registration asked for
# two read scopes. Under DCR the portal names no scope, and an empty request
# is granted every negotiable scope (all five tg advertises), so that failure
# cannot recur from here. mctl-telegram#691 pins the portal's DCR client.
#
# Applying never widens or narrows a live session: the grant is fixed at the
# upstream login done from the dashboard ("Authenticate server").

# `tg` was forgotten from state and is imported back here
# (mctlhq/mctl-gitops#1363). It moved to DCR on 2026-09-26, and dropping the
# manual `auth_credentials` it carried could not be applied as an edit:
# provider 5.24 sends a removed write-only attribute as an explicit null and
# the API refuses the PUT (400 7001 "Expected string, received null"; the
# apply of #1402). #1403 forgot it with a `removed { destroy = false }` block,
# and this import reads it from the API, which returns no auth_credentials --
# so `tg` is in state as DCR, the same as `seerrsense` and `api`.
#
# The lesson for the next server that changes mode: moving a resource from
# manual to DCR is forget + import, not an edit.
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

  # The first upstream: the Phase 0 pilot the portal started with
  # (mctlhq/.github#44).
  description = "First upstream of the private aggregate portal, the Phase 0 pilot. Registered by DCR (pinned client, mctlhq/mctl-telegram#691). Refs mctlhq/.github#35, #44, #137, mctlhq/mctl-gitops#1363."

  secure_web_gateway               = false
  is_shared_oauth_callback_enabled = false

  lifecycle {
    # Same reasoning as projects below: mcp-portal.tf writes the mapping, from
    # allowlists/tg.json (vendored from mctlhq/mctl-telegram).
    ignore_changes = [updated_tools, updated_prompts]
  }
}

# The fourth upstream, and the first registered by dynamic client registration
# rather than by hand.
#
# When this was written every other server was manual, and manual mode costs
# a server the thing this one was registered to test: a manual server's
# capability catalogue is captured
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
    # `tools` and `prompts` are the capability catalogue Cloudflare syncs from
    # the upstream. `updated_tools` / `updated_prompts` are written by the
    # portal resource in mcp-portal.tf, from allowlists/projects.json
    # (vendored from mctlhq/projects-mcp, #1370). Declaring them here too
    # would give this root two writers of one mapping, so they stay ignored.
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
    # Same reasoning as projects above: mcp-portal.tf writes the mapping, from
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
    # Same reasoning as projects above: mcp-portal.tf writes the mapping, from
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
    # Same reasoning as projects above: mcp-portal.tf writes the mapping, from
    # allowlists/seerrsense.json (vendored from mctlhq/seerrsense).
    ignore_changes = [updated_tools, updated_prompts]
  }
}

# `tg` (top of this file) and `api` moved from manual to automatic (DCR) mode
# on 2026-09-26 by the same three-step sequence as `seerrsense` above, once
# each upstream admitted the portal's exact callbacks at its /register:
#
#   - api: registrations persisted in Postgres (mctlhq/mctl-api#400, 4.54.0),
#     with the two callbacks added to OAUTH_ALLOWED_REDIRECT_URIS;
#   - tg:  a pinned client derived from OAUTH_DCR_REDIRECT_URIS
#     (mctlhq/mctl-telegram#691, 0.69.0), exempt from the sweep and the cap.
#
# Both came back ready/connected with a fresh last_synced, the same tool
# catalogue (api 92, tg 36, name for name and in order against
# allowlists/catalogue.json), and the portal mapping untouched -- api's
# fifteen disabled tools stayed disabled. For `tg` this change removes the
# write-only `auth_credentials` the resource used to carry; leaving it would
# have put the server back into manual mode on the next apply.
#
# `api` is adopted here for the first time: the dashboard created it before
# this root existed.
import {
  to = cloudflare_zero_trust_access_ai_controls_mcp_server.api
  id = "${var.account_id}/api"
}

resource "cloudflare_zero_trust_access_ai_controls_mcp_server" "api" {
  account_id = var.account_id
  id         = "api"
  name       = "MCTL API (api.mctl.ai)"
  hostname   = "https://api.mctl.ai/mcp"
  auth_type  = "oauth"

  description = "Third upstream of the private aggregate portal. Registered by DCR (mctlhq/mctl-api#400). Refs mctlhq/.github#35, #137, mctlhq/mctl-gitops#1363."

  secure_web_gateway               = false
  is_shared_oauth_callback_enabled = false

  lifecycle {
    # Same reasoning as projects above: mcp-portal.tf writes the mapping, from
    # allowlists/api.json (vendored from mctlhq/mctl-api).
    ignore_changes = [updated_tools, updated_prompts]
  }
}
