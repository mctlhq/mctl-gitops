# Adopt anthropic-sdk-go v1.74.0's CompactBeforeNextTurn() in the diagnose loop

## Context
mctl-agent's diagnose phase (skill match → diagnose → fix, including the LLMDiagnosis
fallback skill per ADR 0001) drives multi-turn tool calls against the Anthropic API for
tickets that reach that stage of the pipeline. As a multi-turn tool-calling loop runs
longer, the accumulated tool-call context grows, increasing token usage, latency, and
API cost on later turns. `anthropic-sdk-go v1.74.0` (released 2026-09-18) adds
`CompactBeforeNextTurn()` to the tool runner, which can trim growing tool-call context
between turns. The release notes call out no breaking changes, making this a low-risk,
incremental SDK bump with a direct performance/cost benefit on an existing,
frequently-hit code path (LLMDiagnosis and any other diagnose-phase tool-using skill),
rather than new surface area.

## User stories
- AS the mctl-agent operator, I WANT the diagnose loop's tool-call context compacted
  between turns SO THAT long-running diagnose sessions use less Anthropic API token
  budget and complete faster.
- AS a cost owner, I WANT to measure the before/after token usage of the diagnose loop
  SO THAT the benefit of adopting `CompactBeforeNextTurn()` is verified, not assumed.

## Acceptance criteria (EARS)
- WHEN `anthropic-sdk-go` is bumped to v1.74.0 THE SYSTEM SHALL continue to build and
  pass its existing test suite without any breaking-change remediation (per the
  release notes, none is expected).
- WHEN the diagnose loop (LLMDiagnosis skill and any other diagnose-phase code path
  that performs multi-turn tool calls) executes a turn beyond the first THE SYSTEM
  SHALL invoke `CompactBeforeNextTurn()` on the tool runner before issuing the next
  turn's request.
- IF a diagnose session consists of a single turn (no follow-up tool call needed) THEN
  THE SYSTEM SHALL NOT alter its existing single-turn behavior (compaction only applies
  between turns, so single-turn sessions are unaffected).
- WHEN compaction is enabled THE SYSTEM SHALL preserve enough context that diagnosis
  quality (skill confidence / fix correctness, as observed via existing
  ticket-resolution outcomes) does not regress compared to the pre-compaction baseline.
- WHILE this change is being validated THE SYSTEM SHALL record before/after token-usage
  and latency metrics for the diagnose phase (via existing observability, e.g.
  ticket/skill metrics already stored for circuit-breaker purposes) to confirm the
  expected improvement.

## Out of scope
- Changing the rate-limits API `group.display_name` field usage (unrelated, no current
  consumer of `group_type` in mctl-agent to migrate).
- Adopting the Bedrock-specific fixes in v1.74.0 (comma-joined `anthropic-beta` header
  values, mid-stream error frames) — mctl-agent uses the direct Anthropic API per
  `context/architecture.md`, not Bedrock; no action needed there.
- Any change to which skills use the LLM diagnose path, or to the circuit-breaker
  thresholds (explicitly out of scope per `context/architecture.md`'s "What NOT to do"
  list, which prohibits touching circuit breaker thresholds without real prod data).
- Removing or restructuring LLMDiagnosis itself (explicitly prohibited by
  `context/architecture.md`).
