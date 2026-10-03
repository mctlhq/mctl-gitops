# Design: mcp-portal-tool-exposure

## Source commits
- mctl-api:f95ce9b — feat(mcp): dispatch the portal server-auth apply without holding the token
- mctl-api:3b68ce3 — feat(portal): expose every api tool on the aggregate, mctl's own checks decide

## Current state of documentation
- `docs/mcp/overview.md` — existing page. Describes "How Access Works" as a
  three-step model (token validated per request, team-scoped access, full
  audit trail) but never mentions that there are **two distinct connection
  paths** (direct `api.mctl.ai/mcp` vs. the shared Cloudflare/Backstage MCP
  portal aggregate) or that the portal has its own, separately-configured
  tool-visibility allowlist. This is a conceptual gap, not a stale
  statement — nothing currently written is wrong, but a whole access path
  is undocumented.
- `docs/mcp/tools-reference.md` — existing 70-tool reference. No entry for
  `mctl_trigger_portal_server_auth_apply`. The page's `## Tool Annotations`
  section at the very end explains `readOnly`/`write`/`destructive` but has
  no mention of the portal at all.
- `docs/platform/components.md` — describes `mctl-portal` as "Backstage
  developer portal — the UI for browsing and managing services," which is
  accurate for the portal's own UI but doesn't mention that it (or another
  Cloudflare-fronted aggregate) also re-exposes MCP tools from multiple
  upstream servers. `<TODO: confirm with author of 3b68ce3 whether the
  Cloudflare MCP portal aggregate and mctl-portal/Backstage are the same
  deployment or two separate things — the commit message references "the
  Backstage/Cloudflare portal aggregate" and "server api" as one of several
  upstreams ("tg", "seerrsense"), which suggests the aggregate fronts
  multiple MCP servers beyond just mctl-api, but that is not confirmed from
  the diff alone.>`

## Proposed solution
1. **Update** `docs/mcp/overview.md` — add a short new subsection (e.g.
   "Connecting Directly vs. Through the Portal") under `## How Access
   Works`, stating: (a) there are two ways to reach MCTL's MCP tools — a
   direct connection to `api.mctl.ai/mcp`, and the shared Cloudflare MCP
   portal aggregate other MCP-capable surfaces go through; (b) as of
   2026-09-12 the portal aggregate exposes every `mctl-api` tool, not a
   curated subset — the allowlist that used to hide most write/destructive
   tools now only decides visibility; (c) `mctl-api`'s own authentication
   and team-scope/role checks are the actual access control in both cases,
   so seeing a tool through the portal never means you're authorized to
   call it successfully.
2. **Update** `docs/mcp/tools-reference.md` — add
   `mctl_trigger_portal_server_auth_apply` as a new one-row section (there
   is exactly one tool, so a compact section similar in size to the
   existing "Agent Registry" pattern, not a full new functional group).
   State plainly: it dispatches a GitHub Actions workflow in `mctl-gitops`
   that reconciles the portal's own OAuth registration; it requires a
   human approval on a protected GitHub Actions environment before
   anything reaches Cloudflare; and that's why it's annotated
   non-destructive despite triggering an infrastructure-affecting
   workflow — what it *starts* is gated, not what it *does*.
3. Optionally cross-link from `docs/platform/components.md`'s `mctl-portal`
   entry to the new "Connecting Directly vs. Through the Portal" subsection,
   if a human reviewer confirms the mctl-portal/Cloudflare-portal
   relationship noted as a TODO above.

## Alternatives
1. **A full standalone page, `docs/mcp/portal.md`.** Rejected for this
   cycle: the actual delta is a policy statement (everything is visible
   now) plus one new tool — a subsection of the existing Overview page and
   a Tools Reference entry cover it without introducing a new page that
   would mostly duplicate `docs/mcp/overview.md`'s existing structure. If
   the Cloudflare portal grows its own onboarding/config story later, a
   standalone page becomes the better call then.
2. **Put the "everything is now visible" note only in `tools-reference.md`
   next to the new tool, skip `overview.md`.** Rejected: a portal-connected
   reader is far more likely to land on `overview.md` first (it's the
   entry point for "how do I connect and what can I do"), and the
   authorization nuance ("visible ≠ permitted") is exactly the kind of
   thing that belongs in the conceptual overview rather than being
   discoverable only by reading one tool's reference entry.

## Impact
- Does not touch `.vitepress/config.ts` — both changes land inside
  existing pages, no new page/nav entry.
- No mermaid diagram required. A simple two-path bullet list (direct vs.
  portal) is sufficient; the existing `docs/platform/architecture.md`
  System Diagram already shows `clientPortal["Developer Portal UI"]` as
  one client type, which is compatible with this addition without needing
  a diagram edit.
- Coordinate the tool-count bump in `docs/mcp/overview.md` / `tools-reference.md`
  / `docs/reference/faq.md` ("70 tools") with
  `proposals/lifecycle-ownership/` — both proposals add one tool this
  cycle (`mctl_trigger_portal_server_auth_apply` here,
  `mctl_get_lifecycle_ownership` there), so the banner should move from 70
  to 72 once, not be bumped twice independently by two separately-merged
  PRs.
- Applies to the current `main` branch of `mctl-docs`; no versioning split.
