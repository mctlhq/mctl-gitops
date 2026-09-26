# Upgrade anthropic-sdk-go to v1.75.0 for the tool-runner compaction fix

## Context
The sibling proposal `anthropic-sdk-compact-before-next-turn` adopts `anthropic-sdk-go
v1.74.0` and wires `CompactBeforeNextTurn()` into mctl-agent's diagnose-phase tool
runner (used by the LLMDiagnosis skill and any other diagnose-phase code path that
performs multi-turn tool calls) to trim growing tool-call context between turns.
`anthropic-sdk-go v1.75.0` (released 2026-09-22) fixes a correctness bug directly on
that same code path: reply-only parameters were previously left in the tool runner's
compaction request, which could send the API a request containing fields that only
make sense in a reply, not a fresh compacted turn. v1.75.0 removes those reply-only
params from the compaction request. The same release also makes `AddTools()` take
effect immediately (previously could be delayed a turn) and preserves extra fields on
open-object parameter unmarshalling — both of which reduce the risk of subtly wrong
tool definitions or dropped fields reaching the diagnose loop.

This is a small, low-effort follow-up bump (v1.74.0 to v1.75.0, no breaking changes
called out) that closes a real correctness gap in the exact feature the previous
proposal introduces, rather than an independent or speculative change.

## User stories
- AS the mctl-agent operator I WANT the tool-runner's compaction request to exclude
  reply-only parameters SO THAT compacted multi-turn diagnose sessions send well-formed
  requests to the Anthropic API instead of risking malformed or rejected requests.
- AS the mctl-agent maintainer I WANT `AddTools()` to take effect on the very next turn
  SO THAT dynamically registered tools (e.g. from newly loaded YAML or remote skills)
  are available to the diagnose loop without an off-by-one-turn delay.

## Acceptance criteria (EARS)
- WHEN the mctl-agent module is built THE SYSTEM SHALL use `anthropic-sdk-go` at
  version 1.75.0 as declared in `go.mod`.
- WHEN the diagnose-phase tool runner invokes `CompactBeforeNextTurn()` between turns
  THE SYSTEM SHALL send a compaction request that omits reply-only parameters, per the
  v1.75.0 fix.
- WHEN a skill registers a new tool via `AddTools()` during an active diagnose session
  THE SYSTEM SHALL make that tool available starting with the very next turn, not one
  turn later.
- IF the diagnose loop unmarshals an open-object tool parameter containing fields not
  explicitly modeled by mctl-agent's Go structs THEN THE SYSTEM SHALL preserve those
  extra fields rather than silently dropping them.
- WHEN the full existing diagnose-phase / LLMDiagnosis test suite is run after the
  v1.75.0 bump THE SYSTEM SHALL pass without modification, consistent with the release
  notes calling out no breaking changes.

## Out of scope
- Wiring `CompactBeforeNextTurn()` into the tool runner for the first time — that is
  the scope of the sibling proposal `anthropic-sdk-compact-before-next-turn` (v1.74.0).
  This proposal only bumps the already-adopted mechanism to the version that fixes it.
- Adopting `claude-opus-5-5` model support or MCP tool-list pinning (beta), both new in
  v1.75.0 but unrelated to the compaction fix — a separate proposal if/when needed.
- Any change to circuit-breaker thresholds or to which skills use the LLM diagnose
  path (prohibited by `context/architecture.md`'s "What NOT to do" list).
- Deploying to tenant `labs` — mctl-agent runs only in `admins`.
