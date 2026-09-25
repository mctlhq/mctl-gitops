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

  # Each server's synced catalogue: tool names in the order the portal stores
  # them. Committed, not read, because provider 5.24 types the catalogue
  # attribute `tools` as list(map(string)); the API's tool objects are nested,
  # so the attribute is empty in state and in every data source (measured on
  # #1382). scripts/portal-catalogue-drift.py compares this file with the live
  # catalogue nightly.
  portal_catalogue = jsondecode(file("${path.module}/allowlists/catalogue.json")).servers
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
  # Deprecated in provider 5.24, but left out it plans as (known after
  # apply), so the live value is restated.
  allow_code_mode = false

  # `servers` is a set in the provider, so the lexical order of this map's
  # keys is not compared (the import plans 0 to change, #1382).
  servers = [
    for id, s in local.portal_mapping : {
      server_id        = id
      default_disabled = s.default_disabled
      on_behalf        = s.on_behalf
      # null means no override: the portal shows every catalogue prompt.
      updated_prompts = s.updated_prompts
      # Walk the catalogue, not the allowlist: the portal stores exactly one
      # entry per synced tool, in catalogue order. An allowlist entry for a
      # tool the portal has not synced (tg's upstream-gated tools, for one)
      # would be a change the API never keeps -- a diff on every plan -- so
      # it is left out until catalogue.json names the tool. A catalogue tool
      # with no decision fails the lookup; the validator reports it first.
      # The one direction nothing here can close: a tool the portal synced
      # after catalogue.json was last updated gets no entry, so its exposure
      # is the API's default for an unlisted tool until the file catches up.
      # portal-catalogue-drift.py reports that lag nightly (exit 5).
      updated_tools = [
        for name in local.portal_catalogue[id] : {
          name    = name
          enabled = local.portal_decisions[id][name]
        }
      ]
    }
  ]
}
