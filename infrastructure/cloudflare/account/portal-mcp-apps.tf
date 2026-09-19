# The Access application that makes `projects` visible to a person in the MCP
# portal at mcp.mctl.ai.
#
# A portal member is three separate objects, and having two of them is not
# visible as a failure anywhere in the two that exist:
#
#   1. the server resource
#      (cloudflare_zero_trust_access_ai_controls_mcp_server.projects, in
#      infrastructure/cloudflare/portal/mcp-servers.tf),
#   2. its membership in the portal's `servers[]` list, with the tool
#      allowlist on it (mctlhq/projects-mcp scripts/portal-allowlist-apply.sh),
#   3. and THIS: an Access application of type `mcp` whose destination is the
#      server id via the portal. It is what carries the policy deciding which
#      identities the portal may show that server to.
#
# Measured on 2026-09-19, with 1 and 2 both correct — server `ready` /
# `connected` with all 8 tools synced, and a portal `servers[]` holding four
# members with `projects` at 8 of 8 enabled — the portal page still rendered
# "3 enabled servers" for mashkoffdmitry@gmail.com, and the portal's own
# `portal_toggle_single_server` answered `not found` for `projects` while
# listing it among the portal's servers in the same message. Both are this
# application being absent: api, tg and seerrsense each have one, created by
# hand through the dashboard on 2026-09-10, and `projects` -- added by
# Terraform and a membership write -- never got one, because neither of those
# two steps creates it.
#
# Root choice: this is an Access application, so it belongs to the root whose
# credential can write one. infrastructure/cloudflare/portal is applied with a
# token scoped to Account -> MCP Portals alone (see that root's versions.tf)
# and cannot create this; CF_APPLY_TOKEN_ACCOUNT, which applies this root,
# already manages cloudflare_zero_trust_access_application.projects_mcp.
#
# The three pre-existing sibling applications stay out of state for now: they
# are live, unmanaged drift that predates this file, and importing them is its
# own reviewed change rather than a rider on this one.
resource "cloudflare_zero_trust_access_application" "portal_member_projects" {
  account_id = var.account_id
  name       = "MCP server: projects (via portal mcp.mctl.ai)"
  type       = "mcp"

  # The field shape is copied from the live `api` application rather than from
  # documentation: GET /accounts/{account_id}/access/apps/{id} on it returns
  # exactly this destination type with the server id, `allowed_idps: []`,
  # `auto_redirect_to_identity: false` and a 24h session.
  destinations = [
    {
      type          = "via_mcp_server_portal"
      mcp_server_id = "projects"
    },
  ]

  session_duration = "24h"

  # Named addresses, deliberately NOT the "any account from the Google
  # provider" policy that projects-mcp.tf uses for projects.mctl.ai itself.
  #
  # Those are two different doors to the same server and they are meant to
  # differ. A customer reaches https://projects.mctl.ai/mcp directly, as their
  # own connector, and is filtered by their grant once inside. The portal is
  # the owner's private aggregate view of all four upstreams at one URL, and
  # its other three members admit these same two addresses under the same
  # policy name. Widening this one to every Google account would hand any
  # signed-in stranger the aggregate, api and tg included -- the portal's own
  # application (mcp_portal, mcp.mctl.ai) would still refuse them, so it would
  # be a wider grant than it looks, sitting behind a narrower one.
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
