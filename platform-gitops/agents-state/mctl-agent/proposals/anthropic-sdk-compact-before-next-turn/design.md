# Design: anthropic-sdk-compact-before-next-turn

## Current state
Per `context/architecture.md`, mctl-agent's diagnose phase sits in the pipeline
`ticket → evidence → skill match (ranked by confidence + circuit breaker) → diagnose →
fix → PR → notify`. The LLMDiagnosis builtin skill (one of 9 builtin Go skills, see
ADR 0001) and potentially other diagnose-phase logic call the Anthropic API directly
(not via Bedrock) using `anthropic-sdk-go`, performing multi-turn tool calls to gather
evidence and reason about a fix. Context accumulates turn-over-turn within a single
diagnose session; today nothing trims that context, so token usage/latency grow with
session length. There is no `CompactBeforeNextTurn()` call anywhere in the codebase
today because the SDK does not yet expose it at our current pinned version.

## Proposed solution
1. Bump `anthropic-sdk-go` in `go.mod` to `v1.74.0`. Per the release notes, this is a
   non-breaking release (also brings Bedrock header/stream fixes, irrelevant to us
   since we call the Anthropic API directly, and a `group.display_name` rate-limits
   field we don't currently consume).
2. Locate the diagnose-phase tool runner construction (wherever mctl-agent builds/
   drives the multi-turn tool-calling loop for LLMDiagnosis and any other
   diagnose-phase skill that uses tool calls).
3. Call `CompactBeforeNextTurn()` on the tool runner between turns — i.e., after
   receiving a turn's response and before constructing the next turn's request, so that
   growing tool-call history is trimmed before it's sent again. This is purely an
   SDK-runner-level call; it does not change mctl-agent's own skill logic, ranking, or
   circuit-breaker behavior.
4. Validate with existing observability: mctl-agent already tracks skill metrics (used
   by the circuit breaker) — extend that instrumentation minimally, if not already
   present, to also record per-diagnose-session token usage and latency, so the
   before/after comparison in the acceptance criteria has real data rather than
   anecdote.
5. Roll out behind no feature flag (SDK-level, non-breaking, and the release notes
   indicate no compatibility risk) but monitor the first N diagnose sessions post-
   deploy via existing ticket/skill metrics before considering the change "settled."

## Alternatives
- **Do nothing / defer until a future SDK bump forces the issue.** Rejected: this is a
  low-effort (Effort: 2), directly beneficial (Impact: 3) change on a frequently-hit
  code path with no breaking changes called out; deferring has no offsetting benefit.
- **Implement manual context-trimming logic in mctl-agent instead of using the SDK's
  built-in `CompactBeforeNextTurn()`.** Rejected: duplicates functionality the SDK now
  provides natively, adds maintenance burden, and is more likely to introduce subtle
  bugs in what tool-call history gets kept vs. dropped than relying on the
  upstream-tested implementation.
- **Bump to v1.74.0 for other reasons but skip actually wiring in
  `CompactBeforeNextTurn()`.** Rejected: this would take on the (minimal) risk of a
  version bump without capturing the actual benefit that motivates this proposal.

## Platform impact
- **Migrations:** none — no data schema changes; this is an SDK call added to the
  existing diagnose-loop code path.
- **Backward compatibility:** release notes call out no breaking changes for
  `anthropic-sdk-go` v1.74.0. mctl-agent's own API surface (REST/webhook/MCP endpoints)
  is unaffected; this change is internal to the diagnose phase's Anthropic API calls.
- **Resource impact:** expected to *reduce* token usage and latency for multi-turn
  diagnose sessions (the stated goal), i.e., a net positive on Anthropic API cost. Not
  deployed to `labs` (mctl-agent runs only in `admins`), so the `labs` memory-pressure
  constraint from `context/architecture.md` does not apply.
- **Risks and mitigations:**
  - *Risk:* aggressive compaction between turns could trim context the diagnose loop
    actually needs, degrading fix quality or skill-match confidence. *Mitigation:*
    validate with before/after metrics (see task list) on real or replayed diagnose
    sessions before treating the change as fully settled; keep the SDK bump and the
    `CompactBeforeNextTurn()` wiring in a single, easily revertible PR.
  - *Risk:* SDK bump introduces an unrelated regression despite "no breaking changes"
    in the release notes. *Mitigation:* full existing test suite must pass; this is a
    minor/patch-style bump (1.7x → 1.74.x line), lower risk than a major version jump.
