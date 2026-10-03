# Design: mcp-roadmap-control-plane

## Source commits
- mctl-api:a36ebcc — feat(roadmap): read-only epic status and ready work items (#333)
- mctl-api:be13e0c — feat(roadmap): governed epic wave start (#334)
- mctl-api:7ab6e32 — feat(roadmap): refuse a wave for a paused or completed epic

## Current state of documentation
- `docs/platform/roadmap-control-plane.md` — **missing.** No page anywhere
  in `docs-tree.md` mentions "epic", "roadmap", "wave", or a
  `RoadmapPublication` concept.
- `docs/platform/architecture.md` — existing System Diagram + Request Flow
  page (confirmed via a live fetch of the current file). It documents the
  MCP Request and Self-Healing flows but has no mention of a roadmap /
  epic-wave flow. No diagram change requested (same reasoning as the
  `lifecycle-ownership` proposal: the System Diagram is component-level,
  not subsystem-level).
- `docs/mcp/tools-reference.md` — existing 70-tool reference (confirmed via
  live fetch). Organized by functional section (Identity, Tenants,
  Services, Operations & Workflows, Incidents, Domains, Databases, Preview
  Environments, Repositories, Agent Registry, Platform Skills, OpenClaw,
  mctl-agents pipeline controls). No `Roadmap` section exists. The
  tool-count banner on this page ("exposes 70 tools") and the matching
  banners on `docs/mcp/overview.md` ("Tools: 70 (32 read-only, 26 write, 12
  destructive)") and `docs/reference/faq.md` ("70 tools") will need
  bumping — see Impact.
- `docs/mcp/examples.md` — existing natural-language example page
  (confirmed via live fetch), organized by task category. No roadmap/wave
  example.
- `docs/api/index.md` — existing REST reference page (confirmed via live
  fetch: Health, Tenants, Services, Resources, Workflows, Audit,
  Repositories, Operations, Human Input, MCP Endpoint sections). No
  `Roadmap` section; the page states its own goal as "All operations
  available through MCP tools are also available as REST endpoints," which
  this proposal's new REST endpoints would otherwise silently violate.

## Proposed solution
1. **Create** `docs/platform/roadmap-control-plane.md` — a new concept page
   under the "Platform" sidebar group. It explains: what an epic is (an
   `EpicDefinition` published by `mctlhq/.github`), that `mctl-api` is a
   **pure consumer** of the published `RoadmapPublication` and never
   evaluates readiness itself, the ready-set / health shape it reads, the
   provenance fields every answer carries (state/evaluator/source
   revisions, `capturedAt`, age), and the plan-then-start wave flow
   (`mctl_plan_epic_wave` → show the plan → `mctl_start_epic_wave` with the
   plan's exact `plan_hash`/`state_revision`/`items`, unchanged). It states
   explicitly: a `503` means "cannot say," never "nothing is ready"; a wave
   is refused for a paused or completed epic (`7ab6e32`); starting a wave
   never approves a proposal — every started DevLoop still waits for human
   approval; and the epic-status/ready-items/wave tools are currently
   **disabled on the shared MCP portal**, pending an owner decision (stated
   directly in the `a36ebcc`/`be13e0c` commit messages).
2. **Update** `docs/api/index.md` — add a new `## Roadmap` section (placed
   after `## Human Input`, before `## MCP Endpoint`, matching the page's
   existing method-by-method reference style) documenting
   `GET /api/v1/roadmap/epics`, `GET /api/v1/roadmap/epic-status`,
   `GET /api/v1/roadmap/ready`, `POST /api/v1/roadmap/waves/plan`, and
   `POST /api/v1/roadmap/waves/execute`, with a link to the concept page
   for the semantics (readiness, wave refusal codes).
3. **Update** `docs/mcp/tools-reference.md` — add a `## Roadmap Control
   Plane` section (a natural standalone home, similar to "Agent Registry")
   with the four new tools, their parameters, and a link to the concept
   page. Note the portal-disabled status inline, matching how
   `mctl-agents pipeline controls` calls out its own admin-only scope.
4. **Update** `docs/mcp/examples.md` — add a `## Roadmap Control Plane`
   example showing the plan → start flow end to end, including what a
   `plan_stale` / `publication_too_old` / `invalid_selection` refusal means
   and what to do about each.
5. **Update** `docs/platform/architecture.md` — add a one-line cross-
   reference in the Request Flow section (same pattern as the
   `lifecycle-ownership` proposal's Block 5), linking to the new concept
   page.
6. **Update** `.vitepress/config.ts` sidebar — add the new page to the
   `Platform` group, after `Components`.

## Alternatives
1. **Fold the concept explanation into `docs/mcp/tools-reference.md`
   instead of a standalone concept page.** Rejected: the plan/start
   contract (plan hash, state revision, refusal codes) is dense enough,
   and shared between the REST docs and the MCP tool docs, that a single
   concept page both reference is more maintainable — same precedent as
   `docs/platform/lifecycle-ownership.md` (proposed last week) being a
   standalone page referenced from both `docs/api/index.md` and
   `docs/mcp/tools-reference.md`.
2. **Skip the REST section in `docs/api/index.md` since the wave tools are
   portal-disabled anyway.** Rejected: portal-disabled only affects the
   *shared aggregate MCP portal*; the REST endpoints and the MCP tools on
   the direct `api.mctl.ai/mcp` connector are both live today for any admin
   token, and `docs/api/index.md`'s own stated parity goal would otherwise
   be silently broken for this feature — the same reasoning the
   `lifecycle-ownership` proposal used for its own REST section.

## Impact
- Touches `.vitepress/config.ts` sidebar (`Platform` group — one new
  entry). No nav-bar change needed.
- No mermaid diagram is strictly required; a short sequence diagram of
  plan → show → start → per-item outcome (`started` / `already_running` /
  `already_exists` / `failed`) would aid readers and is recommended as a
  nice-to-have in the concept page (see `proposed-content.md`), consistent
  with `docs/reference/diagrams.md`'s guidance to use a diagram for a state
  machine a paragraph can't convey concisely.
- Tool-count banners: `docs/mcp/overview.md` ("Tools: 70..."),
  `docs/mcp/tools-reference.md` ("exposes 70 tools"), and
  `docs/reference/faq.md` ("70 tools") all need the count bumped by +4 for
  this proposal's tools. This is now the **third** proposal in flight this
  cycle touching the same banners (`lifecycle-ownership` +1,
  `lifecycle-recovery-tools` +5, this proposal +4) — whoever implements
  first should bump the banner to the cumulative total once all three are
  known to be landing, not bump it three times independently.
  `<TODO: confirm final cumulative tool count and read/write/destructive
  split with the mctl-api maintainer before publishing any of the three
  banner edits>`.
- Applies to the current `main` branch of `mctl-docs`; no versioning split
  needed (the site is not currently version-branched).
