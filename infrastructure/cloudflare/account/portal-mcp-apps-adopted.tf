# The three portal member applications that predate portal-mcp-apps.tf:
# `tg`, `seerrsense` and `api`. Each is the third object of a portal member
# (see the header of portal-mcp-apps.tf) -- an Access application of type
# `mcp` whose destination is the server via the portal at mcp.mctl.ai.
#
# All three were created by hand in the dashboard on 2026-09-10 and stayed
# unmanaged, so a dashboard edit to them was invisible to cloudflare-drift.
# They are adopted here under mctlhq/mctl-gitops#1416 (refs #1092), import
# only: every field below is the live value, read on 2026-09-27 from
# GET /accounts/{account_id}/access/apps/{id}, and nothing is harmonised with
# the siblings in portal-mcp-apps.tf. In particular:
#
#   - session_duration is the dashboard default 24h, not the siblings' 8760h.
#     Raising it is a behaviour change with its own plan, not part of an
#     adoption.
#   - The cookie flags are not written: the provider refuses them on
#     `type = "mcp"` (unlike mcp_portal in portal-app.tf), and the managed
#     siblings, which omit them too, read zero-diff in drift.
#
# `oauth_configuration` is unset, as it is live.
#
# Policies. Each application has exactly one policy, "Phase 0 pilot users"
# (allow; include mashkoffdmitry@gmail.com and mashkovdm.dm@gmail.com; no
# exclude, no require). All three are app-scoped (`reusable: false`) and are
# absent from GET /accounts/{account_id}/access/policies, so there is no
# standalone cloudflare_zero_trust_access_policy to import: each is referenced
# by its id, as mcp_portal references 5f0102c7-... in portal-app.tf. Writing
# them inline instead would make the provider rewrite each policy as part of
# the import.
#
# Ids are literal rather than looked up: a data source over this root's
# read-only plan identity returned an empty list instead of an error once
# already (projects-mcp.tf). They identify objects in this account and are
# not secrets.
locals {
  adopted_member_apps = {
    tg = {
      app_id    = "3a41c8db-a877-46af-bd3d-752fab0117a5"
      policy_id = "d8cf354f-7f2d-4111-a19c-8585ff1b77fb"
    }
    seerrsense = {
      app_id    = "7a3689c6-cb60-48c0-a28b-63b84a2ee560"
      policy_id = "5fe6ee32-db08-4f36-ab93-532058a61ec3"
    }
    api = {
      app_id    = "a6f30a66-f0eb-4241-84e8-b5c80be81abd"
      policy_id = "eb2997ba-d5ea-4f52-8d2c-0f1838a732ce"
    }
  }
}

import {
  to = cloudflare_zero_trust_access_application.portal_member_tg
  id = "accounts/${var.account_id}/${local.adopted_member_apps.tg.app_id}"
}

resource "cloudflare_zero_trust_access_application" "portal_member_tg" {
  account_id = var.account_id
  name       = "MCP server: tg (via portal mcp.mctl.ai)"
  type       = "mcp"

  destinations = [
    {
      type          = "via_mcp_server_portal"
      mcp_server_id = "tg"
    },
  ]

  allowed_idps              = []
  auto_redirect_to_identity = false

  session_duration = "24h"

  policies = [
    {
      id         = local.adopted_member_apps.tg.policy_id
      precedence = 1
    },
  ]
}

import {
  to = cloudflare_zero_trust_access_application.portal_member_seerrsense
  id = "accounts/${var.account_id}/${local.adopted_member_apps.seerrsense.app_id}"
}

resource "cloudflare_zero_trust_access_application" "portal_member_seerrsense" {
  account_id = var.account_id
  name       = "MCP server: seerrsense (via portal mcp.mctl.ai)"
  type       = "mcp"

  destinations = [
    {
      type          = "via_mcp_server_portal"
      mcp_server_id = "seerrsense"
    },
  ]

  allowed_idps              = []
  auto_redirect_to_identity = false

  session_duration = "24h"

  policies = [
    {
      id         = local.adopted_member_apps.seerrsense.policy_id
      precedence = 1
    },
  ]
}

import {
  to = cloudflare_zero_trust_access_application.portal_member_api
  id = "accounts/${var.account_id}/${local.adopted_member_apps.api.app_id}"
}

resource "cloudflare_zero_trust_access_application" "portal_member_api" {
  account_id = var.account_id
  name       = "MCP server: api (via portal mcp.mctl.ai)"
  type       = "mcp"

  destinations = [
    {
      type          = "via_mcp_server_portal"
      mcp_server_id = "api"
    },
  ]

  allowed_idps              = []
  auto_redirect_to_identity = false

  session_duration = "24h"

  policies = [
    {
      id         = local.adopted_member_apps.api.policy_id
      precedence = 1
    },
  ]
}
