# Bound implementer-owned local verification to the remaining execution envelope

## Context

mctl-agents#423 moved unbounded CI-log retrieval out of the implementer's
execution envelope and added a shielded, bounded teardown when the outer
`anyio.fail_after` fires with a delegated child still live
(`orchestrator/run_implementer.py:1937`, `:1992`). Live acceptance of that
work on `mctl-agents` 1.51.0 against mctlhq/mctl-telegram#652 showed a second,
distinct hole. The implementer never attempted a forbidden CI-log self-fetch —
`options._ci_log_guard_hook` was never triggered — it did legitimate local
reproduction instead: it launched `go test -race ./... > /tmp/test-race.log
2>&1 &` and then polled that background process across repeated Bash calls
(cumulative ~354s, ~607s, ~859s). The `ci-remediation` envelope of 1020s
expired while the delegated `implementer` sub-agent was still live, so
`_run_implementer_agent` raised `ImplementerOrphanedSubagent` and the run
exited `EXIT_ORPHANED_SUBAGENT = 46`. The shepherd classified it blamelessly
(`run_shepherd._followup_code_sets()` harness set), `review_attempts` stayed
0 → 0, `harness_failures` went 0 → 1, and no PR mutation happened at all.

The classification was right; the shape is wrong. Nothing inside a running
implementer knows how much of its envelope is left, so an agent-issued command
is bounded only by the Claude Code CLI's own tool timeout — which, per ADR-011,
backgrounds a slow command instead of failing it — and an explicitly
backgrounded command (`cmd &`) escapes task accounting entirely, because
`subagent_wait.AWAITED_TASK_TYPES` deliberately excludes background shells. A
legitimate verification step can therefore outlive the remaining envelope and
leave the agent task live at outer expiry. This proposal makes every
implementer-owned command derive its own bound from the REMAINING envelope
minus a teardown reserve, denies detached launches that would escape that
bound, and turns the exhausted case into a structured, blameless outcome the
shepherd can read — so `EXIT_ORPHANED_SUBAGENT` returns to being the safety
net it was designed as rather than the normal result of a slow test suite.

## User stories

- AS the Tier 2 implementer I WANT every command I run to be bounded by the
  budget I actually have left SO THAT a slow test suite ends in a result I can
  act on instead of killing the whole run.
- AS the Tier 3 shepherd I WANT a cut-short local verification to arrive as a
  structured, machine-readable outcome SO THAT I can distinguish it from a lost
  run and from a content failure, and charge neither `review_attempts` nor a
  spurious `harness_failures` tick for prose I have to guess at.
- AS a platform operator I WANT a single number I can point at for "no
  implementer command may run longer than this, and none may outlive the
  envelope" SO THAT a CI-remediation tick converges instead of burning
  `MAX_HARNESS_FAILURES` on a `go test -race`.
- AS an on-call engineer I WANT no orphaned child process, background shell or
  sub-agent to survive an implementer run SO THAT the pod exits clean and the
  worktree is not being mutated by anything after the driver returns.

## Acceptance criteria (EARS)

- WHEN `_run_implementer_agent` enters its outer `anyio.fail_after(envelope_s)`
  THE SYSTEM SHALL compute one absolute monotonic deadline for the run and make
  it available to the agent-facing `PreToolUse` guard for every work class
  (`review`, `ci-remediation`, `mixed`), not only the CI classes.
- WHEN the agent issues a `Bash` tool call THE SYSTEM SHALL derive that call's
  wall-clock bound as `min(IMPLEMENTER_COMMAND_TIMEOUT_SECONDS,
  remaining_envelope - IMPLEMENTER_TEARDOWN_RESERVE_SECONDS)` and apply it to
  the command before it starts.
- WHEN a derived command bound is applied THE SYSTEM SHALL enforce it at the
  operating-system level (a `timeout`-wrapped invocation that signals the
  command's process group), not only by the tool-input `timeout` field, because
  the CLI's own tool timeout backgrounds rather than fails an over-running
  command (ADR-011, "Containment").
- WHILE a run is inside its envelope THE SYSTEM SHALL never widen a command's
  bound above what the caller requested — clamping is one-directional.
- IF an agent-issued command would detach from task accounting (a trailing `&`
  async-list operator, `nohup`, `setsid`, `disown`, or a `Bash` tool input
  carrying `run_in_background: true`) THEN THE SYSTEM SHALL deny the tool call
  with a reason telling the agent to run the command synchronously under the
  bound it has.
- IF `remaining_envelope - IMPLEMENTER_TEARDOWN_RESERVE_SECONDS` is below
  `IMPLEMENTER_MIN_COMMAND_BUDGET_SECONDS` THEN THE SYSTEM SHALL deny further
  command execution with a reason instructing the agent to commit what it has
  and record the bounded outcome, rather than admitting a command that cannot
  finish.
- WHILE commands are being clamped or denied THE SYSTEM SHALL record each event
  (clamped, denied-background, denied-exhausted, the bound applied, and a
  truncated command label) in a per-run, orchestrator-owned ledger — never in
  model prose.
- WHEN a run ends with no new commits AND the ledger shows the command budget
  was exhausted THE SYSTEM SHALL exit
  `EXIT_VERIFICATION_BUDGET_EXHAUSTED` (51) and write the ledger summary as
  JSON to the existing `--refusal-out` path.
- WHEN the shepherd receives exit 51 THE SYSTEM SHALL classify it
  `FollowupKind = "harness"` — blameless, never charging `review_attempts`,
  bounded by `MAX_HARNESS_FAILURES` exactly as
  `EXIT_ORPHANED_SUBAGENT` and `EXIT_CI_EVIDENCE_INSUFFICIENT` already are —
  and include the structured reason in its log line and terminal note.
- WHEN a run ends with new commits THE SYSTEM SHALL push and exit `EXIT_OK`
  even if some verification was cut short, and SHALL print the ledger summary
  so the truncation is visible in the Argo log.
- WHILE the teardown reserve is unspent THE SYSTEM SHALL preserve enough budget
  to cancel the active command, drain delegated children
  (`subagent_wait.drain_until_settled`), write the structured marker, and
  return before the outer bound fires.
- WHEN `_run_implementer_agent` returns for any reason THE SYSTEM SHALL leave
  no live agent-launched child process: a bounded command is terminated and
  then killed after a fixed grace.
- WHEN a verification command completes well inside the remaining budget (the
  ordinary case — a unit-test run early in the envelope) THE SYSTEM SHALL let
  it finish untouched, with no premature cancellation and no behavioural change
  from today.
- WHEN `orchestrator/options.py` is imported THE SYSTEM SHALL validate that
  every work class's envelope can satisfy `IMPLEMENTER_TEARDOWN_RESERVE_SECONDS
  + IMPLEMENTER_MIN_COMMAND_BUDGET_SECONDS + IMPLEMENTER_MUTATION_RESERVE_SECONDS`
  and, on violation, log loudly and clamp the teardown reserve rather than raise
  — the same "loud and harmless, never silent and unbounded" policy
  `_positive_seconds` and `validate_budget_contract` already follow.
- IF the `timeout` binary is unavailable in the runtime image THEN THE SYSTEM
  SHALL log a loud warning once per run and fall back to tool-input clamping
  plus the detachment denials, rather than failing the run or silently running
  unbounded.

## Out of scope

- Raising `IMPLEMENTER_TIMEOUT_SECONDS`, `IMPLEMENTER_TIMEOUT_CEILING_SECONDS`
  or the `ci-remediation` envelope. Explicitly forbidden by the issue.
- Any `go test -race`-specific or language-specific handling. The boundary is
  generic over the `Bash` tool.
- The broader bounded implement → verify → fix inner loop (mctl-agents#429).
  This proposal supplies an execution-envelope input to it; it does not
  implement it.
- Re-opening #427's CI-log self-fetch guard. It remains valid and untouched;
  the new guard is composed alongside it via `options._compose_hooks`.
- Changing `EXIT_ORPHANED_SUBAGENT` semantics, its exit code, or its place in
  the shepherd's harness set. It stays the safety net.
- Streaming partial command output back to the shepherd, or persisting test
  logs anywhere outside the clone.
- The `issue-investigator` and `service-agent` drivers. They have no outer
  `fail_after` at all (see the `SERVICE_AGENT_DRAIN_TIMEOUT_SECONDS` comment in
  `orchestrator/options.py`), so there is no remaining-envelope to derive from;
  extending the guard there is follow-up work.

## Open questions

- Exact default for `IMPLEMENTER_TEARDOWN_RESERVE_SECONDS`. 120s is proposed:
  it covers `IMPLEMENTER_TEARDOWN_GRACE_SECONDS` (15s), the agent's closing
  turn, and the commit, without eating the mutation reserve. It is deliberately
  NOT `IMPLEMENTER_DRAIN_TIMEOUT_SECONDS` (300s), which would leave a
  900s `review` envelope with too little command budget to be useful. Proceeding
  with 120s, env-overridable and validated at import.
- Whether a cut-short verification that still produced a commit should also
  surface to the shepherd structurally (e.g. as a note on the follow-up), or
  only in the Argo log. Proceeding with log-only: the commit is the outcome, and
  adding a status field here would collide with mctl-agents#428's
  implementation-completion/handoff contract.
- Whether `updatedInput` on a `PreToolUse` `allow` decision is honoured by the
  pinned `claude-agent-sdk` / CLI pair. `PreToolUseHookSpecificOutput` declares
  it (`claude_agent_sdk/types.py`), but the behaviour must be pinned by a test
  and a version assertion (task T8); if it is not honoured, the fallback is to
  DENY the unbounded form with a reason carrying the exact `timeout`-wrapped
  command to re-issue, which needs no SDK support at all.
- Whether the bounded-outcome exit code should be a new 51 or a reuse of
  `EXIT_CI_EVIDENCE_INSUFFICIENT` (50). Proceeding with 51: 50 means "the
  evidence I was handed cannot support a decision", this means "I ran out of
  budget while producing my own evidence" — different operator action.
</content>
</invoke>
