# Design: lifecycle-ownership

## Source commits
- mctl-api:5a1da2d — feat(lifecycle): add the lifecycle ownership store
- mctl-api:e7aee63 — feat(lifecycle): expose ownership over HTTP with an explicit auth boundary
- mctl-api:1064b2c — feat(lifecycle): add mctl_get_lifecycle_ownership
- mctl-api:783a238 — feat(lifecycle): reject the deprecated ?id on the list path

## Current state of documentation
- `docs/platform/lifecycle-ownership.md` — **missing.** No page describes the
  ownership store, ADR-009/010, or the status vocabulary at all.
- `docs/api/index.md` — existing REST reference page (Tenants, Services,
  Resources, Workflows, Audit, Repositories, Operations, MCP Endpoint
  sections). No `Lifecycle Ownership` section exists; the page has no
  mention of `/api/v1/lifecycle/*` anywhere.
- `docs/mcp/tools-reference.md` — existing 70-tool reference, organized by
  functional section (Identity, Tenants, Services, Operations & Workflows,
  Incidents, Domains, Databases, Preview Environments, Repositories, Agent
  Registry, Platform Skills, OpenClaw, mctl-agents pipeline controls). No
  section for `mctl_get_lifecycle_ownership`; the tool count banner ("70
  tools") on this page and on `docs/mcp/overview.md` / `docs/reference/faq.md`
  would also need bumping once this (and the portal-tool-exposure proposal's
  new tool) are counted — see Impact below.
- `docs/mcp/examples.md` — existing natural-language example page, organized
  by task category (Getting Oriented, Deploying, Investigating Issues,
  Scaling, Domains, Previews, Incident Response, Multi-Step Workflows). No
  lifecycle-ownership example.
- `docs/platform/architecture.md` — existing system diagram and request-flow
  page. Does not mention the lifecycle ownership store as a control-plane
  component (reasonable: the diagram is already fairly high-level, so this
  proposal only asks for a one-line cross-reference, not a diagram change).

## Proposed solution
1. **Create** `docs/platform/lifecycle-ownership.md` — a new concept page
   under the existing "Platform" sidebar group, alongside Overview /
   Architecture / Components. It explains: what an entity/phase/owner is,
   the two currently-legal `(kind, phase)` pairs and their staleness bounds,
   the closed state vocabulary (`active`, `handing-off`, `released`,
   `terminal`) versus the *derived*, read-only status vocabulary (`healthy`,
   `stuck`, `dead`, `handing-off`, `handoff-stalled`, `released`,
   `terminal`, `unknown`), why a `503` from this subsystem must never be
   read as "nobody owns this," and that ownership grants no GitHub merge or
   approval authority. This is the anchor page the other three updates link
   back to.
2. **Update** `docs/api/index.md` — add a new `## Lifecycle Ownership`
   section (placed after `## Operations`, before `## MCP Endpoint`, matching
   the page's existing method-by-method reference style) documenting the
   read endpoints (`GET /api/v1/lifecycle/ownership`,
   `GET /api/v1/lifecycle/ownership/record`,
   `GET /api/v1/lifecycle/ownership/batch`,
   `GET /api/v1/lifecycle/events`) and noting that the six write endpoints
   exist but are intended for internal platform actors (DevLoop, shepherd,
   reconciler), not manual/human calls — with a link to the concept page for
   the semantics.
3. **Update** `docs/mcp/tools-reference.md` — add a `## Lifecycle Ownership`
   section (a natural home: standalone like "Agent Registry", since this
   tool doesn't fit the existing Tenants/Services/etc. groups) with the one
   new tool, its parameters, and a link to the concept page. Mark it
   admin-only, matching the style already used for the "mctl-agents pipeline
   controls" section.
4. **Update** `docs/mcp/examples.md` — add one short example under a new
   `## Lifecycle Ownership` heading.
5. **Update** `docs/platform/architecture.md` — add a one-line mention in
   the `mctl-api` control-plane description (or a "See also" style note)
   linking to the new concept page. No diagram change requested; the
   existing System Diagram is already component-level, not
   subsystem-level, and adding a lifecycle-ownership node would be
   disproportionate to the diagram's current granularity.
6. **Update** `.vitepress/config.ts` sidebar — add the new page to the
   `Platform` group.

## Alternatives
1. **Fold the concept explanation into `docs/api/index.md` instead of a
   standalone page.** Rejected: the status vocabulary and takeover
   semantics are conceptually dense enough (and shared between the REST
   docs and the MCP tool docs) that duplicating them in both places would
   drift; a single concept page that both reference is more maintainable,
   consistent with how `docs/security/authentication.md` is a standalone
   concept page that both `docs/api/index.md` and `docs/mcp/overview.md`
   link back to.
2. **Document only the MCP tool (skip the REST section) since the write
   endpoints are internal-actor-only.** Rejected: the four read endpoints
   are reachable by any admin token today, mirror what the MCP tool does
   under the hood, and `docs/api/index.md`'s stated goal ("All operations
   available through MCP tools are also available as REST endpoints") would
   otherwise be silently broken for this feature.

## Impact
- Touches `.vitepress/config.ts` sidebar (`Platform` group — one new
  entry). No nav-bar change needed.
- No mermaid diagram is proposed for the new page (a simple state-hierarchy
  bullet list is sufficient for the vocabulary; a sequence diagram of
  acquire → progress → handoff → release could be a good follow-up once a
  human reviewer confirms the exact flow, but that's additive, not blocking
  this proposal).
- Tool-count banners: `docs/mcp/overview.md` ("Tools: 70 (32 read-only, 26
  write, 12 destructive)"), `docs/mcp/tools-reference.md` ("exposes 70
  tools"), and `docs/reference/faq.md` ("70 tools") all need the count
  bumped by the tools added in this proposal and in
  `proposals/mcp-portal-tool-exposure/` (`mctl_get_lifecycle_ownership` +
  `mctl_trigger_portal_server_auth_apply` = +2 tools, both read-only /
  non-destructive respectively — exact new breakdown needs confirmation:
  `<TODO: confirm exact current tool count and read/write/destructive split
  with mctl-api maintainer before publishing, since two proposals both add
  a tool this cycle and the banners must only be bumped once>`).
- Applies to the current `main` branch of `mctl-docs`; no versioning split
  needed (the site is not currently version-branched per
  `context/docs-tree.md`).
