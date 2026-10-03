# Design: anthropic-sdk-v175-compaction-fix

## Current state
Per `context/architecture.md`, mctl-agent's diagnose phase sits in the pipeline
`ticket → evidence → skill match (ranked by confidence + circuit breaker) → diagnose →
fix → PR → notify`, and calls the Anthropic API directly (not via Bedrock) using
`anthropic-sdk-go`. The sibling proposal `anthropic-sdk-compact-before-next-turn` bumps
the SDK to v1.74.0 and wires `CompactBeforeNextTurn()` into the diagnose-phase tool
runner to trim tool-call context between turns of a multi-turn diagnose session (used
by the LLMDiagnosis builtin skill, see ADR 0001, and any other diagnose-phase skill
using tool calls). As shipped in v1.74.0, that compaction path is affected by a bug: the
runner's generated compaction request retains reply-only parameters that should not be
present on what is effectively a fresh (compacted) turn.

## Proposed solution
1. Bump `anthropic-sdk-go` in `go.mod` from `v1.74.0` to `v1.75.0`
   (`go get github.com/anthropics/anthropic-sdk-go@v1.75.0 && go mod tidy`). This is a
   dependency-only change: no call sites in mctl-agent need to change, because the fix
   is internal to the SDK's tool-runner compaction-request construction, and
   `CompactBeforeNextTurn()` keeps the same call signature.
2. Sequence this after (or combined with, if not yet merged) the
   `anthropic-sdk-compact-before-next-turn` proposal's task 3 (wiring in
   `CompactBeforeNextTurn()`), so the compaction call site and its fix land together
   rather than shipping a known-buggy compaction path first.
3. Re-run the diagnose-phase test suite, including the multi-turn compaction test added
   by the sibling proposal, to confirm requests sent after compaction no longer include
   reply-only fields (verified via a mocked/recorded Anthropic API transcript, not a
   live API call in CI).
4. No new instrumentation is needed beyond what the sibling proposal already adds
   (per-diagnose-session token usage and latency via existing skill/ticket metrics).

## Alternatives
- **Stay on v1.74.0 and treat the reply-only-params issue as a latent, low-probability
  bug.** Rejected: the fix is already available upstream, the bump is a patch-level
  version bump with no breaking changes, and shipping a known-buggy compaction request
  shape when a fix exists is unnecessary risk for near-zero effort.
- **Skip v1.75.0 and wait for a later SDK version that bundles more fixes.** Rejected:
  there's no reason to defer a already-released, non-breaking correctness fix on a code
  path we are actively adopting this cycle; batching for its own sake adds delay without
  benefit.
- **Reimplement compaction request construction in mctl-agent to strip reply-only
  params ourselves, instead of taking the upstream fix.** Rejected: duplicates SDK
  internals we don't want to own, and is strictly worse than consuming the
  already-tested upstream fix.

## Platform impact
- **Migrations:** none — dependency version bump only, no data schema or API changes.
- **Backward compatibility:** release notes call out no breaking changes for v1.75.0.
  mctl-agent's own REST/webhook/MCP API surface is unaffected; this is internal to the
  diagnose phase's Anthropic API calls.
- **Resource impact:** neutral to slightly positive — a correctly-shaped compaction
  request is, if anything, smaller than one carrying stray reply-only fields. Not
  deployed to `labs` (mctl-agent runs only in `admins`), so the `labs` memory-pressure
  constraint from `context/architecture.md` does not apply.
- **Risks and mitigations:**
  - *Risk:* landing this bump before the sibling `CompactBeforeNextTurn()` wiring is
    merged could create a merge-order dependency that's easy to get backwards.
    *Mitigation:* explicitly sequence as "wire compaction on v1.74.0 or later, ship on
    v1.75.0" — if the sibling proposal hasn't merged yet, bump straight to v1.75.0 as
    part of that same PR instead of bumping twice.
  - *Risk:* an unrelated regression slips in despite "no breaking changes" in the
    release notes. *Mitigation:* full existing test suite must pass; this is a single
    patch-version bump (v1.74.0 to v1.75.0), lower risk than a major version jump.
