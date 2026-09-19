# Document the lifecycle ownership store (concept, REST API, MCP tool)

## Context
Between 2026-09-12 and 2026-09-14, `mctl-api` shipped a complete new subsystem:
the lifecycle ownership store (ADR-009 / ADR-010). Four commits introduce
externally-reachable surface:

- `5a1da2d` — the store itself (`internal/lifecycle/store.go`, `types.go`):
  a Postgres-backed record of which actor (a DevLoop workflow, the shepherd,
  a PR steward, a reconciler, or a human codeowner) currently holds
  responsibility for advancing a given entity (a pull request or a
  devloop-backed proposal) through a given lifecycle phase (`implement` or
  `review-remediation`).
- `e7aee63` — a REST endpoint family under `/api/v1/lifecycle/*`
  (`internal/api/handlers_lifecycle.go`), admin-only, with an explicit
  two-layer authorization model (transport admin check vs. record-level
  owner/epoch check) and a `503` (never `404`) when the store itself is
  unreachable.
- `1064b2c` — a new MCP tool, `mctl_get_lifecycle_ownership`
  (`internal/mcp/lifecycle.go`), the read-only surface for an operator or an
  MCP client to inspect ownership, including a derived status vocabulary and
  a "divergence" comparison against the legacy DevLoopWorkflow liveness
  check.
- `783a238` — closes out a one-release deprecation: the old `?id=` query
  parameter on the list endpoint (`GET /api/v1/lifecycle/ownership`) now
  returns `400` naming the replacement (`GET
  /api/v1/lifecycle/ownership/record`) instead of silently delegating.

Nothing on `docs.mctl.ai` describes any of this today. `docs/api/index.md`
has no `/api/v1/lifecycle/*` section, `docs/mcp/tools-reference.md` has no
entry for `mctl_get_lifecycle_ownership`, and `docs/platform/architecture.md`
does not mention the ownership store as a platform component. This is a
whole new, already-shipped API/MCP surface with zero doc coverage — the
highest-impact gap identified in this week's scan.

## User stories
- AS a platform admin diagnosing a stuck DevLoop or PR-review-remediation
  cycle, I WANT to understand what "lifecycle ownership" means and how to
  read the status vocabulary (`healthy`, `stuck`, `dead`, `handing-off`,
  `handoff-stalled`, `released`, `terminal`, `unknown`) SO THAT I can tell
  whether an entity is actually stuck versus just slow, and whether it is
  safe for another actor to take over.
- AS a developer building an MCP client or automation against `mctl-api`, I
  WANT a documented example of calling `mctl_get_lifecycle_ownership` in both
  "single record" and "list" mode SO THAT I can query ownership without
  reverse-engineering the tool's parameters from trial and error.
- AS an operator or integrator calling the REST API directly, I WANT the new
  `/api/v1/lifecycle/*` endpoints documented (methods, required query
  params, status codes) SO THAT I know these endpoints exist, that they are
  admin-only, and what `409`/`412`/`503` mean here specifically (they are
  not generic errors).
- AS a caller who previously relied on `?id=` on the list endpoint, I WANT
  the docs to state the current (non-deprecated) contract directly SO THAT I
  don't have to discover the `400` by trial and error.

## Acceptance criteria (EARS)
- WHEN a reader opens `docs/platform/lifecycle-ownership.md` THE SYSTEM
  SHALL explain what a lifecycle phase and an owner are, list the two
  currently-legal (kind, phase) pairs (`pull-request/review-remediation`,
  `devloop-proposal/implement`), and explain the closed status vocabulary
  and what `held` versus `dead` means for takeover decisions.
- WHEN a reader opens `docs/api/index.md` THE SYSTEM SHALL show a
  "Lifecycle Ownership" section listing every `/api/v1/lifecycle/*`
  endpoint (method, path, purpose, admin-only note) and the meaning of
  `409`/`412`/`503` on this endpoint family specifically.
- IF a reader wants to call the new MCP tool THEN THE SYSTEM SHALL provide
  a worked example on `docs/mcp/tools-reference.md` (parameter table) and
  `docs/mcp/examples.md` (a natural-language example plus what the tool
  returns).
- WHEN a reader opens `docs/platform/architecture.md` THE SYSTEM SHALL
  contain at least a one-line pointer to the lifecycle ownership concept
  page, since ownership sits inside the control plane the diagram already
  shows.
- WHILE the ownership store's write endpoints (`acquire`, `progress`,
  `handoff/*`, `release`, `terminal`) are internal-actor-only (DevLoop,
  shepherd, reconciler) THE SYSTEM SHALL say so explicitly, so a
  human reader does not attempt to drive ownership by hand outside of
  automation.
- IF a reader is still on the deprecated `?id=` list-endpoint pattern THEN
  THE SYSTEM SHALL NOT document that pattern as valid; the docs describe
  only the current, non-deprecated contract (list vs. `/record`).

## Out of scope
- Documenting `internal/lifecycle/diverge.go`'s exact divergence-class
  taxonomy at the Go-type level (beyond the reader-facing "why does
  divergence matter" explanation already needed for the MCP tool).
- A migration guide for any caller still using the deprecated `?id=`
  parameter (none is known to exist per the commit message; `mctl-agents`
  1.45.0 already reads `/record`).
- The `POST /api/v1/lifecycle/ownership/recover` endpoint and any other
  lifecycle route added by the ~80 `fix(lifecycle)` hardening commits not
  individually cited in this proposal's source-commit set — those may
  warrant a follow-up proposal once attributed to a specific commit.
- ADR-009 / ADR-010 themselves (they live in `mctl-agents`/`mctl-gitops`,
  not `docs.mctl.ai`, per the researcher's note).
