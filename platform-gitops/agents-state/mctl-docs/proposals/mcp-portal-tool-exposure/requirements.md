# Document the widened MCP-portal tool surface and the new server-auth-apply tool

## Context
On 2026-09-12, `mctl-api` shipped two related changes to how MCP tools are
exposed through the shared Cloudflare MCP portal (the multi-upstream MCP
aggregate that Backstage / `app.mctl.ai` and other portal-connected clients
go through, as distinct from connecting directly to `api.mctl.ai/mcp`):

- `3b68ce3` — per owner decision `mctlhq/.github#35`, the portal's
  allowlist (`docs/portal-allowlist.json` in `mctl-api`) now exposes
  **every** `mctl-api` tool on the aggregate, not a curated read-only
  subset. Concretely, 41 mutating tools flip from disabled to enabled on
  the portal, alongside the 33 read-only ones already there. Safety no
  longer comes from the allowlist deciding what's visible — it comes from
  `mctl-api`'s own authentication, team scope, and role checks deciding
  whether a call actually succeeds. The allowlist is now "visibility, not
  permission."
- `f95ce9b` — a new MCP tool, `mctl_trigger_portal_server_auth_apply`, lets
  an admin dispatch the `cloudflare-apply.yml` GitHub Actions workflow in
  `mctl-gitops` (which reconciles the portal's own upstream OAuth
  registration/scopes) without holding a GitHub token themselves. The tool
  only *starts* a gated, human-approved workflow run — it never touches
  Cloudflare directly.

Neither `docs/mcp/overview.md` nor `docs/mcp/tools-reference.md` currently
mentions the Cloudflare/Backstage portal aggregate as a distinct connection
path at all, let alone that its tool surface differs (or, as of this
change, no longer differs in *visibility* but still differs in that the
portal is user-blind — the API's own auth is what decides). A
portal-connected user reading today's docs would under-estimate what's
callable through the portal, and no reader has any way to discover the new
`mctl_trigger_portal_server_auth_apply` tool at all.

## User stories
- AS a developer connecting through the Backstage/Cloudflare MCP portal
  (rather than a direct connection to `api.mctl.ai/mcp`), I WANT to know
  that the portal aggregate exposes every `mctl-api` tool, and that my
  effective permissions are still decided by `mctl-api`'s own
  authentication and role checks (not by the portal) SO THAT I understand
  what's actually callable and why "the portal shows it" does not mean "I'm
  allowed to run it."
- AS a platform admin whose Cloudflare-side OAuth registration for the
  portal has drifted from what's committed in `mctl-gitops`, I WANT to know
  `mctl_trigger_portal_server_auth_apply` exists and what it does (and does
  not do) SO THAT I can dispatch the reconciliation workflow from an
  MCP-capable client instead of needing GitHub UI access myself.
- AS a security-conscious reader, I WANT the docs to be explicit that this
  tool starts a workflow that still requires a human-approved GitHub
  Actions environment gate before anything touches Cloudflare SO THAT I
  don't mistake "an MCP tool can trigger this" for "an MCP tool can apply
  Cloudflare config unattended."

## Acceptance criteria (EARS)
- WHEN a reader opens `docs/mcp/overview.md` THE SYSTEM SHALL explain that
  MCTL's tools are reachable two ways — a direct connection to
  `api.mctl.ai/mcp`, and the shared Cloudflare/Backstage MCP portal
  aggregate — and that both surfaces enforce the same `mctl-api`
  authentication and authorization; the portal allowlist controls
  visibility only.
- WHEN a reader opens `docs/mcp/tools-reference.md` THE SYSTEM SHALL list
  `mctl_trigger_portal_server_auth_apply` with its parameters (none),
  return value, and a plain statement that it starts a gated,
  human-approved workflow rather than applying anything itself.
- IF a reader wants to call `mctl_trigger_portal_server_auth_apply` THEN
  THE SYSTEM SHALL provide a worked example showing the call and its
  return shape.
- WHILE `mctl_trigger_portal_server_auth_apply` is annotated non-destructive
  (because what it *dispatches* is gated, not what it *does*) THE SYSTEM
  SHALL explain that distinction explicitly rather than leaving the reader
  to infer it from the annotation alone.

## Out of scope
- A full description of the Cloudflare MCP portal's own OAuth-registration
  mechanics or the `cloudflare-apply.yml` workflow's internal steps (that
  detail belongs in `mctl-gitops`, not `docs.mctl.ai`, unless a future
  gap explicitly asks for it).
- Re-documenting the full 41-tool allowlist diff tool-by-tool; the docs
  should state the *policy* (everything is now visible, `mctl-api`'s own
  checks decide access) rather than enumerate every previously-hidden
  tool.
- Any change to `docs/security/authorization.md`'s description of
  `mctl-api`'s own team-scope/role model — that model is unchanged by this
  commit set; only what the portal exposes changed.
