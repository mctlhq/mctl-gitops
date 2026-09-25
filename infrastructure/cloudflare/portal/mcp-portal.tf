# The MCP portal itself, and which of each upstream's tools it exposes.
#
# Until this file, six things wrote `servers[].updated_tools` on this one
# object: a script in each of four service repos, a hand-run PUT for
# `seerrsense`, and the dashboard. This root becomes the single writer
# (mctlhq/mctl-gitops#1370). The DECISION about a tool stays with the repo
# that ships it: each owning repo's docs/portal-allowlist.json is vendored
# byte-identical into allowlists/<id>.json and checked by
# scripts/validate-portal-allowlists.py. Everything about a server's
# membership that is not the owning repo's call -- default_disabled,
# on_behalf, the prompt override, and `api`'s literal tool list until it is
# vendored -- is in allowlists/mapping.json, which the validator reads too,
# so neither side needs an HCL parser.
#
# `mcp-portal-controls.json` and scripts/portal-controls-apply.sh still
# describe the portal's switches until #1370's retirement PR deletes them.
# The values agree; the script only ever re-asserts them.

locals {
  portal_mapping = jsondecode(file("${path.module}/allowlists/mapping.json")).servers

  # server id -> { tool name -> enabled }, from the vendored file, or from
  # mapping.json's literal list for a server that is not vendored. Two
  # filtered comprehensions rather than one conditional: the two sources are
  # tuples of different shapes, and a non-vendored server has no file to read.
  portal_decisions = merge(
    {
      for id, s in local.portal_mapping : id => {
        for t in jsondecode(file("${path.module}/allowlists/${id}.json")).tools : t.name => t.enabled
      } if s.vendored
    },
    {
      for id, s in local.portal_mapping : id => {
        for t in s.updated_tools : t.name => t.enabled
      } if !s.vendored
    },
  )

  # Each server's synced catalogue, in the order the portal stores it. The
  # four servers this root manages come from their own resources; `api` and
  # `seerrsense` are mapped on the portal without a resource here (#1363), so
  # they are read. A server in mapping.json with no entry here fails the plan
  # loudly on the lookup below, which is the intended behaviour.
  portal_catalogue = {
    tg         = cloudflare_zero_trust_access_ai_controls_mcp_server.tg.tools
    projects   = cloudflare_zero_trust_access_ai_controls_mcp_server.projects.tools
    alice      = cloudflare_zero_trust_access_ai_controls_mcp_server.alice.tools
    coolify    = cloudflare_zero_trust_access_ai_controls_mcp_server.coolify.tools
    api        = data.cloudflare_zero_trust_access_ai_controls_mcp_server.api.tools
    seerrsense = data.cloudflare_zero_trust_access_ai_controls_mcp_server.seerrsense.tools
  }
}

data "cloudflare_zero_trust_access_ai_controls_mcp_server" "api" {
  account_id = var.account_id
  id         = "api"
}

data "cloudflare_zero_trust_access_ai_controls_mcp_server" "seerrsense" {
  account_id = var.account_id
  id         = "seerrsense"
}

# Adopting the live portal, the same pattern mcp-servers.tf uses for `tg`.
# Nothing is written to Cloudflare until an approved cloudflare-apply run.
import {
  to = cloudflare_zero_trust_access_ai_controls_mcp_portal.mcp
  id = "${var.account_id}/mcp"
}

resource "cloudflare_zero_trust_access_ai_controls_mcp_portal" "mcp" {
  account_id = var.account_id
  id         = "mcp"
  hostname   = "mcp.mctl.ai"

  # Copied from the live object (read 2026-09-25) so the import is a pure
  # adoption. The description is out of date -- the portal has carried six
  # servers, not only tg, since 2026-09-24 -- and correcting it is a
  # separate, visible change rather than part of the import.
  name        = "mctl private aggregate (mcp.mctl.ai)"
  description = "Private aggregate portal. Never a public connector. Phase 0: tg only, fail-closed allowlist. Refs mctlhq/.github#35."

  secure_web_gateway = false
  code_mode          = "off"
  # allow_code_mode (false live) is deprecated in provider 5.24 and is
  # optional+computed, so it is left to state rather than restated here.

  servers = [
    for id, s in local.portal_mapping : {
      server_id        = id
      default_disabled = s.default_disabled
      on_behalf        = s.on_behalf
      # null means no override: the portal shows every catalogue prompt.
      updated_prompts = s.updated_prompts
      # Walk the catalogue, not the file: the portal stores exactly one entry
      # per synced tool, in catalogue order. A file entry for a tool the
      # portal has not synced (tg's upstream-gated tools, for one) would be
      # a change the API never keeps -- a diff on every plan -- so it is left
      # out until the tool appears in the catalogue, at which point it enters
      # the plan by itself.
      updated_tools = [
        for t in local.portal_catalogue[id] : {
          name    = t["name"]
          enabled = local.portal_decisions[id][t["name"]]
        } if contains(keys(local.portal_decisions[id]), t["name"])
      ]
    }
  ]
}
