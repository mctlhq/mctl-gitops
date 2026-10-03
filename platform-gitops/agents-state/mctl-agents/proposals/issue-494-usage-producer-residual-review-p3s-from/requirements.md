# Usage producer: residual review P3s from #491

## Context

The model-usage producer landed in `orchestrator/usage_ledger.py` (mctlhq/.github#50,
ADR-012) and is fed from `tracing.agent_run`'s `AgentRunObserver.observe`
(`orchestrator/tracing.py:845`). Three review rounds on #491 approved it at
`8e07baf`; issue #494 records the four P3 findings that were left rather than
opening a fourth round. They are all about the truthfulness and the structural
safety of what the producer writes, not about new capability: `recorded_at` is
stamped on the delivery thread instead of at the turn it describes, the
`trace_id` / `span_id` pair that ADR-012's correlation contract says is carried
directly is never sent, the observer calls the recorder outside its own
`try`, and `UsageRecorder.records_for` is documented as pure while it can
mutate `_warned` and reads delivery-thread state (`_seen`, `_baseline`) from
the caller's thread.

Each one matters for a different reason. A `recorded_at` taken on the delivery
thread is normally milliseconds late, but behind a retrying batch against a
degraded mctl-api it is seconds or more late, which makes the ledger's own
timestamp useless for the one question a FinOps consumer asks of it ("when was
this quota spent?"). The missing `trace_id` / `span_id` means a usage row
cannot be joined to the trace of the run that produced it, which is exactly
the per-invocation correlation ADR-012 promises where `temporal_workflow_id`
alone is per-execution. The `try` placement holds today only because
`UsageRecorder.observe` guards itself — moving the call inside makes "a trace
can never fail an execution" (`orchestrator/tracing.py` rule 2) structural
rather than dependent on another module's internals. And a method documented
as pure but reading another thread's state is an invitation for a future
caller to use it on the hot path. The SIGTERM flush of the same review round
is tracked separately in #493 and is not part of this proposal.

## User stories

- AS a FinOps consumer of the usage ledger I WANT `recorded_at` to be the time
  the turn was observed SO THAT a slow or retrying delivery does not shift the
  apparent time of the spend.
- AS an operator investigating one expensive agent run I WANT the usage row to
  carry the W3C `trace_id` and `span_id` of that run SO THAT I can pivot from
  a cost row to the trace of the execution that caused it.
- AS a driver author (investigator, implementer, shepherd) I WANT usage
  recording to be structurally incapable of raising into my message loop SO
  THAT bookkeeping can never fail a run.
- AS a maintainer of `orchestrator/usage_ledger.py` I WANT no public method
  that reads the delivery thread's state while claiming to be pure SO THAT the
  single-writer rule the module documents stays true.

## Acceptance criteria (EARS)

Timestamp

- WHEN `UsageRecorder.observe` accepts a `ResultMessage` THE SYSTEM SHALL
  capture the observation timestamp on the calling thread, before the job is
  submitted to the delivery worker.
- WHEN the delivery worker builds the records of that message THE SYSTEM SHALL
  use the captured timestamp as `recorded_at` for every record of that
  message, unchanged by retries or queue delay.
- WHILE a batch is being retried against a degraded mctl-api THE SYSTEM SHALL
  keep `recorded_at` equal to the value captured at observation time.
- WHEN `recorded_at` is serialised THE SYSTEM SHALL keep the current format:
  UTC ISO-8601 with a `Z` suffix.
- WHEN the ADR-012 amendment is updated THE SYSTEM SHALL state that
  `recorded_at` is the time the producer observed the turn in the agent
  process, not the time the record was delivered or stored.

Trace correlation

- WHEN `tracing.agent_run` enters and tracing is on THE SYSTEM SHALL build its
  `UsageRecorder` with the W3C `trace_id` and `span_id` of the `invoke_agent`
  span, passed through the `**correlation` keywords of
  `UsageRecorder.from_env`.
- WHEN a record is built for a recorder that was given those ids THE SYSTEM
  SHALL include `trace_id` and `span_id` fields whose values are the
  lowercase hex ids of the W3C pair (32 hex digits and 16 hex digits).
- IF tracing is off, or there is no recording span, or the traceparent is not
  a valid non-zero W3C version-00 value THEN THE SYSTEM SHALL omit both fields
  entirely rather than send empty or zero ids.
- WHILE tracing is off THE SYSTEM SHALL keep recording usage exactly as it
  does today (the usage ledger is not optional; tracing is).
- IF deriving the trace ids raises for any reason THEN THE SYSTEM SHALL log
  once and continue with a recorder that carries no trace ids.

Structural safety of the observer

- WHEN `AgentRunObserver.observe` is called THE SYSTEM SHALL invoke the usage
  recorder from inside the method's own `try`, ahead of the
  `self._root.recording` check, so a message is offered to the recorder
  whether or not the span records.
- IF the usage recorder raises THEN THE SYSTEM SHALL swallow it, log it once
  through `tracing._warn_once`, and return normally to the driver's message
  loop.
- WHEN `agent_run` is used with tracing off THE SYSTEM SHALL still hand every
  SDK message to the recorder through the no-op observer.

Purity of the inspection helper

- WHEN the producer's public surface is reviewed THE SYSTEM SHALL contain no
  method that claims purity while mutating `_warned` or reading `_seen` /
  `_baseline` from a thread other than the delivery thread:
  `UsageRecorder.records_for` is removed.
- WHEN `test_correlation_comes_from_the_runner_pod_environment` asserts the
  correlation fields THE SYSTEM SHALL let it read the record actually queued
  and delivered (observe, then flush, then read the captured request body)
  instead of calling a plan-only helper.
- WHILE a recorder is live THE SYSTEM SHALL keep the delivery thread the only
  reader and writer of `_seen` and `_baseline`.

Non-regression

- WHILE this change is in effect THE SYSTEM SHALL keep every behaviour the
  #491 tests pin: per-(session, model) deltas, `(session_id, result_uuid,
  model_key)` identity, the "may have landed" stickiness, the writer-token
  only credential, the https-only transport, the `atexit` flush, and that no
  record field can carry prompt or completion text.
- WHEN the change is complete THE SYSTEM SHALL pass `uv run pytest tests/`,
  `uv run ruff check orchestrator config tests` and `uv run mypy`.

## Out of scope

- The SIGTERM flush (#493). Nothing here changes `flush`, `FLUSH_TIMEOUT_SECONDS`
  or the `atexit` hook.
- Any change to what mctl-api stores, to the row id derivation, to pricing, or
  to the `/api/v1/usage/records` request shape beyond adding the two nullable
  correlation fields ADR-012 already lists.
- Per-turn span attribution: the `span_id` sent is the `invoke_agent` span of
  the run, not the `chat <model>` span of the individual turn.
- Emitting cost, `retry_attempt`, `devloop_stage`, `target_repo`,
  `issue_number` or `pr_number` — fields ADR-012 lists but #491 did not
  populate and #494 does not ask for.
- Documenting `MCTL_USAGE_WRITER_TOKEN` in `.env.example` (absent today; a
  separate housekeeping concern).
- Any change to the tracing span shape, the redaction allowlist in
  `orchestrator/tracing_sdk.py`, or the drivers in `run_implementer.py`,
  `run_issue_investigator.py`, `run_shepherd.py`.

## Open questions

- Does `POST /api/v1/usage/records` (mctl-api#385) already accept `trace_id`
  and `span_id`, and does it ignore or reject fields it does not know? ADR-012
  lists both as nullable schema-v1 fields, so the reasonable interpretation is
  that they are accepted; if mctl-api rejects unknown fields with a 4xx, the
  producer would log "not delivered (HTTP 4xx ...)" for every batch. Proceeding
  on the ADR's contract, with the mitigation recorded in design.md (a client
  error is not retried, recording stays non-fatal, and the change is one
  revertible commit).
- `trace_id` is already an overloaded name in this repo:
  `orchestrator/execution_identity.py:390` carries a 32-hex `trace_id` that is
  an execution-identity id, not necessarily an OTel trace id. Assumed here:
  the usage record's `trace_id` is the W3C/OTel one, as the ADR-012 "OpenTelemetry
  mapping" section implies. The amendment will say so explicitly.
- Should the ids be sent as the raw `traceparent` string instead of a split
  pair? ADR-012 names the fields `trace_id / span_id`, so the split pair is
  used; if a consumer later wants the sampled flag, that is a follow-up.
- Whether the four P3s should land as one commit or four. Assumed one PR, four
  reviewable commits or one squashed commit, since they touch two files and
  share the test file.
