# Validate Claude Haiku 5.5 on the inbound-events session and gate a reversible labs rollout

## Context

The interactive remote-control session in `mctl-claude-remote` takes its model from
`CLAUDE_REMOTE_MODEL` (`entrypoint.sh`, pinned into `/workspace/.claude/settings.json`
as `.model`). The image default is the floating `haiku` alias, but the labs deployment
overrides it with `CLAUDE_REMOTE_MODEL: "sonnet"` in
`mctl-gitops/platform-gitops/services/labs/claude-remote/values.yaml`. The override
exists because of #66: on the previous Haiku generation the session that runs the
`mctl-events` Channel wrote a fake acknowledgement to `/tmp` with Bash instead of
calling `mcp__mctl-events__ack_event`. Every entry stayed pending, `max_inflight`
saturated and the adapter stopped reading for four days.

Claude Haiku 5.5 (released 2026-10-07) is a candidate to replace Sonnet for this
session on cost grounds. The issue asks for proof, on the real inbound-events path,
that Haiku 5.5 does not repeat the #66 failure, a recorded comparison with a Sonnet
baseline, and only then a deliberate, reviewable switch of the labs value to the
explicit model id `claude-haiku-5-5`, with a one-variable rollback to `sonnet`. The
pass criterion is binary: zero fake acknowledgements and zero handled-but-unacked
events.

## User stories

- AS the platform operator I WANT a repeatable, evidence-producing validation of a
  candidate model against the events Channel SO THAT a model change cannot silently
  kill event consumption again.
- AS the platform operator I WANT a recorded Haiku 5.5 vs Sonnet comparison
  (ack correctness, latency, tokens, cost) SO THAT the GO/NO-GO decision is reviewable.
- AS the platform operator I WANT the labs rollout to be a single GitOps value with a
  documented, tested rollback to `sonnet` SO THAT a regression is reverted in one commit.
- AS a future maintainer I WANT the comments in `entrypoint.sh` and `values.yaml` to
  state which models are validated for the Channel and why SO THAT #66 history is not
  lost and the guidance is not stale.

## Acceptance criteria (EARS)

- WHEN `CLAUDE_REMOTE_MODEL=claude-haiku-5-5` is set THE SYSTEM SHALL write
  `"model": "claude-haiku-5-5"` into `/workspace/.claude/settings.json` unchanged (the
  value passes the existing `*[!A-Za-z0-9._-]*` guard) and the pinned Claude Code
  version (`CLAUDE_CODE_NPM_VERSION`, currently 2.1.280) SHALL start a session on it.
- WHEN a validation run completes THE SYSTEM SHALL produce a per-event report that,
  for every event audited as `delivered`, states whether an `acked` audit record from
  `ack_event` exists, its `outcome`, and whether the session transcript contains a real
  `mcp__mctl-events__ack_event` tool_use carrying that `event_id`.
- IF the transcript contains a Bash/Write tool call that simulates an acknowledgement
  (for example writes an `ack`-named file under `/tmp` or echoes an acknowledgement
  payload) THEN THE SYSTEM SHALL flag the event as a fake acknowledgement and fail the run.
- IF an event was handled (hydration tool call present) but no `acked` record exists
  THEN THE SYSTEM SHALL count it as handled-but-unacked and fail the run.
- IF the session's text claims hydration or acknowledgement succeeded for an event
  without the corresponding tool call, or after the tool call returned an error, THEN
  THE SYSTEM SHALL flag it as fabricated success and fail the run.
- WHILE a validation run is in progress THE SYSTEM SHALL keep the event protocol
  unchanged: the CLAUDE.md contract, `INSTRUCTIONS` in `events/mctl_events/channel.py`,
  the `ack_event` schema and `max_inflight` SHALL NOT be relaxed to suit the model.
- WHEN the validation event set has been delivered and handled THE SYSTEM SHALL show the
  consumer group's `pending` back at 0 and the adapter still reading subsequent entries.
- WHEN the validation covers failure paths (hydration unavailable, tool error,
  malformed/rejected envelope) THE SYSTEM SHALL record that the model acknowledged with
  `outcome=failed` or `ignored` (or that the adapter rejected the envelope) and never
  reported success.
- WHEN the same bounded event set is run on `sonnet` and on `claude-haiku-5-5` THE
  SYSTEM SHALL record for each: handled+acked rate, missing/false ack rate, tool-call
  correctness, per-event latency, input/output tokens, estimated cost, malformed tool
  output.
- IF the Haiku 5.5 run has zero fake acks, zero handled-but-unacked events, zero
  fabricated success and a drained `pending` THEN the result SHALL be recorded as GO and
  the companion GitOps change SHALL set `CLAUDE_REMOTE_MODEL: "claude-haiku-5-5"` with an
  updated comment that keeps #66 as historical context and names `sonnet` as rollback.
- IF any of those counts is non-zero THEN the result SHALL be recorded as NO-GO with the
  exact failing event ids and transcript excerpts, and labs SHALL stay on `sonnet`.
- WHEN labs runs on `claude-haiku-5-5` after a GO THE SYSTEM SHALL be observed through the
  audit stream for a soak window and the soak evidence SHALL be attached before #66 is
  considered resolved.
- WHEN `CLAUDE_REMOTE_MODEL` is changed back to `sonnet` THE SYSTEM SHALL re-pin
  `settings.json` `.model` on the next start (existing `ensure_json` repair path) and the
  rollback SHALL have been exercised once and recorded.

## Out of scope

- `PR_STEWARD_MODEL` and the pr-steward ticks (they pass `--model` explicitly).
- `mctl-agents` model policy (mctlhq/mctl-agents#600).
- Changing the image default `haiku` alias in `entrypoint.sh`.
- Any change to the event protocol, the `ack_event` tool, routing policy or
  `max_inflight` defaults.
- Treating vendor benchmarks as evidence.

## Open questions

- The live validation and the soak need a real session with Valkey, Telegram MCP and
  Anthropic credentials; the Tier 2 implementer cannot run them. This proposal assumes
  the implementer ships the evaluator, runbook, comment/docs updates and tests, and an
  operator executes the live runs and fills in the results record. The GitOps flip is a
  separate, operator-reviewed `mctl-gitops` PR opened only after GO.
- Whether `claude-haiku-5-5` is accepted by Claude Code 2.1.280 is unverified. If it is
  not, a `CLAUDE_CODE_NPM_VERSION` bump becomes a prerequisite and should be a separate
  PR (it changes the PTY-launch and native-pin surface tested in `events/tests`).
- Soak length and minimum consecutive-event count are not specified; this proposal
  assumes at least 20 consecutive allowed events per model in validation (mixed
  `github.pull_request.*` and `telegram.message.*`) and a 72-hour labs soak with at
  least 20 real events, both recorded in the results file.
- Validation environment: a separate consumer group/stream on the platform Valkey (or a
  preview deployment) is assumed so test events do not reach the production labs group;
  the exact location is the operator's choice.
