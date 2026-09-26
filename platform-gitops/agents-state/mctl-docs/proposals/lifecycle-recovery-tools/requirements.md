# Document lifecycle-ownership recovery actions (fence / handoff / retry / reconcile)

## Context
On 2026-09-19, `mctl-api` shipped a three-layer extension to the lifecycle
ownership store (proposed for documentation last week in
`proposals/lifecycle-ownership/`, not yet implemented on `docs.mctl.ai`):
guarded operator recovery transitions. `cacd7e3` adds four named store-level
transitions (fence a dead claim, request a handoff off a stuck owner, retry
a stalled handoff, request a reconcile); `f93d0fd` exposes them plus a
conflict-evidence read over HTTP (`GET /api/v1/lifecycle/ownership/conflict`
+ four `POST .../recovery/*` routes); `e7ce245` wraps all five in MCP tools
(`mctl_inspect_lifecycle_conflict`, `mctl_fence_lifecycle_claim`,
`mctl_request_lifecycle_handoff`, `mctl_retry_lifecycle_handoff`,
`mctl_request_lifecycle_reconcile`), all confirmed present in this agent's
live tool list today. This is genuinely new, distinct surface on top of last
week's base ownership-store gap — it lets a human operator safely unblock a
stuck or dead claim instead of only observing ownership read-only — and it
needs its own doc coverage even though it depends on the base concept page
landing first.

## User stories
- AS a platform admin investigating a stuck PR-review-remediation cycle or a
  stalled DevLoop, I WANT to know which recovery action applies to which
  situation (dead → fence, stuck → handoff, stalled handoff → retry, any →
  reconcile-request) SO THAT I pick the transition that actually matches
  what the store currently says, instead of guessing.
- AS a platform admin about to call a destructive recovery tool
  (`mctl_fence_lifecycle_claim`, `mctl_request_lifecycle_handoff`), I WANT
  to know that I must read `mctl_inspect_lifecycle_conflict` first for the
  exact precondition values (`expected_owner_type/id`, `expected_epoch`,
  `expected_version`) SO THAT my call doesn't fail with a `412` because I
  guessed at stale values.
- AS a reader of the concept page, I WANT to understand that none of these
  five tools grants GitHub merge or approval authority SO THAT I don't
  conflate "I fenced the claim" with "I can now merge the PR myself."
- AS a developer calling the REST API directly, I WANT the five
  `/api/v1/lifecycle/ownership/*` recovery endpoints documented (request
  body shape, status codes `409`/`412`) SO THAT I can build tooling without
  reverse-engineering the Go handlers.

## Acceptance criteria (EARS)
- WHEN a reader opens the "Recovery" section of `docs/platform/lifecycle-ownership.md`
  THE SYSTEM SHALL map each of the four mutating actions (fence, handoff,
  retry, reconcile) onto the specific derived status (`dead`, `stuck`,
  `handoff-stalled`, any) that licenses it, referencing the status
  vocabulary table already defined earlier on that page rather than
  re-defining it.
- WHEN a reader opens the "Recovery" section THE SYSTEM SHALL state that
  every mutating call fails closed on a precondition mismatch (`412`,
  naming what moved) and that `mctl_inspect_lifecycle_conflict` is the
  required first step for obtaining current precondition values.
- IF a reader wants to call any of the five new MCP tools THEN THE SYSTEM
  SHALL provide the tool's parameters (including which ones require
  `confirm="yes"`) and at least one worked example in `docs/mcp/examples.md`.
- IF a reader wants to call the REST equivalents THEN THE SYSTEM SHALL
  document the five endpoints under the same `## Lifecycle Ownership`
  section of `docs/api/index.md` that the base proposal introduces, with
  request body shape and the `409`/`412` semantics specific to recovery.
- WHILE this proposal's target page (`docs/platform/lifecycle-ownership.md`)
  does not yet exist THE SYSTEM SHALL make the dependency on
  `proposals/lifecycle-ownership/` landing first explicit in `design.md`,
  and `proposed-content.md` SHALL be written as a diff against that other
  proposal's own `proposed-content.md` output rather than assuming an
  already-live page.
- WHEN a reader opens `docs/mcp/tools-reference.md` THE SYSTEM SHALL clearly
  distinguish the one read-only tool (`mctl_inspect_lifecycle_conflict`)
  from the two destructive tools requiring `confirm="yes"`
  (`mctl_fence_lifecycle_claim`, `mctl_request_lifecycle_handoff`) and the
  two non-destructive mutating tools (`mctl_retry_lifecycle_handoff`,
  `mctl_request_lifecycle_reconcile`).

## Out of scope
- Re-documenting the base ownership concepts (entity/phase/owner, the
  closed status vocabulary, the `503` ≠ `404` distinction) — those are
  `proposals/lifecycle-ownership/`'s responsibility; this proposal only
  adds the "Recovery" section on top.
- A migration guide — this is new surface, not a breaking change.
- The exact advisory-locking implementation detail inside
  `internal/lifecycle/recovery.go` (read-then-write shape) beyond the
  reader-facing "every precondition fails closed" statement already needed.
- Deciding whether any of the four mutating recovery tools should be
  enabled on the shared MCP portal — out of scope per
  `docs/portal-allowlist.json`'s current disabled state for all four
  (only the read tool is enabled, per the commit message); that is
  `proposals/mcp-portal-tool-exposure/`'s territory.
