# Document the Roadmap Control Plane (epics, ready work items, waves)

## Context
Three commits landed in `mctl-api` on 2026-09-23 (`a36ebcc`, `be13e0c`,
`7ab6e32`) that introduce a brand-new, externally reachable "Roadmap Control
Plane" surface: a read model over the `RoadmapPublication` that
`mctlhq/.github` publishes to its `roadmap-state` branch (epic status, ready
work items, health/drift), plus a governed "plan, then start" flow for
kicking off a wave of `DevLoopWorkflow`s against an epic's ready items. The
surface ships as both REST (`GET /api/v1/roadmap/epics`,
`GET /api/v1/roadmap/epic-status`, `GET /api/v1/roadmap/ready`,
`POST /api/v1/roadmap/waves/plan`, `POST /api/v1/roadmap/waves/execute`) and
four new MCP tools (`mctl_get_epic_status`, `mctl_get_ready_work_items`,
`mctl_plan_epic_wave`, `mctl_start_epic_wave`) — all confirmed present in
this agent's own live tool list today. `docs.mctl.ai` currently has zero
mentions of "epic", "roadmap", or "wave" anywhere in its tree
(`context/docs-tree.md`), so a reader has no way to discover this surface,
understand what a "wave" does, or learn the safety guarantees (a wave never
approves anything; a `503` means "cannot say", never "nothing is ready";
a wave for a paused or completed epic is refused) baked into the design.

## User stories
- AS a platform admin I WANT to read the current status of a roadmap epic
  (lifecycle, goal, ready work items, health/drift) SO THAT I can decide
  whether it is safe to start more work on it without reading raw
  `mctlhq/.github` manifests by hand.
- AS a platform admin I WANT to understand what "planning" vs. "starting" a
  wave means, and what each refusal code (`plan_stale`,
  `publication_too_old`, `invalid_selection`) tells me to do next, SO THAT I
  can drive the roadmap control plane confidently from an MCP client without
  guessing at retry logic.
- AS a developer integrating with the REST API directly (not through MCP) I
  WANT the `/api/v1/roadmap/*` endpoints documented with request/response
  shapes SO THAT I can build tooling against them without reading Go source.
- AS a reader of the Architecture page I WANT to know that the Roadmap
  Control Plane exists and how it fits into the control plane SO THAT I can
  place it correctly relative to the MCP server and Argo Workflows.

## Acceptance criteria (EARS)
- WHEN a reader opens `docs/platform/roadmap-control-plane.md` THE SYSTEM
  SHALL explain what an epic, a ready work item, a ready set, and a wave
  are, and SHALL state explicitly that `mctl-api` is a pure consumer of the
  published `RoadmapPublication` — it never evaluates readiness itself.
- WHEN a reader opens `docs/platform/roadmap-control-plane.md` THE SYSTEM
  SHALL document the plan-then-start flow (`mctl_plan_epic_wave` →
  `mctl_start_epic_wave`) including that starting a wave never approves a
  proposal, and that a wave is refused for a paused or completed epic.
- IF a reader wants to call `mctl_get_epic_status`, `mctl_get_ready_work_items`,
  `mctl_plan_epic_wave`, or `mctl_start_epic_wave` THEN THE SYSTEM SHALL
  provide the tool's parameters, return shape, and at least one worked
  example in `docs/mcp/examples.md`.
- IF a reader wants to call the REST equivalents THEN THE SYSTEM SHALL
  document `GET /api/v1/roadmap/epics`, `GET /api/v1/roadmap/epic-status`,
  `GET /api/v1/roadmap/ready`, `POST /api/v1/roadmap/waves/plan`, and
  `POST /api/v1/roadmap/waves/execute` in `docs/api/index.md`, consistent
  with that page's stated goal that every MCP-exposed operation is also a
  REST endpoint.
- WHEN a reader opens `docs/platform/architecture.md` THE SYSTEM SHALL
  mention the Roadmap Control Plane as a component of `mctl-api`'s control
  plane, with a link to the new concept page.
- WHILE the two wave tools (`mctl_plan_epic_wave`, `mctl_start_epic_wave`)
  and the two epic-read tools are disabled on the shared MCP portal (per the
  commit messages, "pending an owner decision") THE SYSTEM SHALL state this
  explicitly rather than implying the tools are available everywhere.
- WHEN a reader encounters a `503` from any roadmap endpoint THE SYSTEM
  SHALL make clear this means "cannot say" / "readiness is UNKNOWN", never
  "nothing is ready" — mirroring the same fail-safe convention documented
  for the lifecycle-ownership store.

## Out of scope
- Documenting the `mctlhq/.github` roadmap manifest format itself (epic
  definitions, `ready.py` evaluation logic) — that lives in the `.github`
  repo, not `docs.mctl.ai`, which only documents what `mctl-api` exposes.
- A migration guide — this is new surface, not a breaking change to
  existing surface.
- The eventual decision on whether the wave/epic tools are enabled on the
  shared MCP portal — that is `proposals/mcp-portal-tool-exposure/`'s
  territory, not this proposal's.
- Video tutorials or localisation.
