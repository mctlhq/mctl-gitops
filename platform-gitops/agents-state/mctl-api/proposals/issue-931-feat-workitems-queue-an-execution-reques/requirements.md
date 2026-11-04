# Queue a work-item execution request while an execution is active, behind a switch that is off by default

## Context

Today `Store.CreateExecutionRequest` (`internal/workitems/execution_requests.go`) calls
`checkRunnable` before the INSERT. `checkRunnable` returns
`ConflictError{ErrExecutionActive}` as soon as the work item has a Pending or Running
execution, so the request is refused (409 `execution_active`) and nothing is stored. The
idempotency key is remembered only after a successful insert. mctl-agents#992 keeps the
DevLoop's canonical `we_` execution open through the whole implement run, which widens
the refusal window from "investigate -> approval" to minutes. The owner requires that a
request arriving inside that window is not lost: it must be stored durably and delivered
after the execution closes, keeping the original actor, intent and idempotency key. It
must not create duplicates, a stale `expected_state_version` must be handled correctly,
and it must work whether implement ends in Success, Failure, Cancel or Timeout.

This proposal is the mctl-api half. It has four parts, all behind a new kill switch
`MCTL_EXECUTION_REQUEST_QUEUE_WHILE_ACTIVE` (default off):

- Create stores a `pending` request when the only blocker is an active execution.
- Claim never hands out a request whose work item still has an open execution.
- A reconciler closes Temporal-owned executions whose owning run has already closed, so
  queued requests are not blocked forever.
- A real-API test proves that a second approval grant can be requested and decided on
  the still-open canonical `we_`.

With the switch off, behaviour is exactly today's.

## User stories

- AS a person on Telegram or MCP I WANT my resume request to be accepted while the
  DevLoop is still implementing SO THAT I do not have to notice the refusal and resend it.
- AS the mctl-agents execution-request dispatcher I WANT claim to return only requests
  whose work item has no open execution SO THAT I never deliver an update into a loop
  that is still implementing.
- AS a platform operator I WANT an execution left open by a Temporal run that no longer
  runs to be closed automatically SO THAT a queued request cannot be blocked forever.
- AS a platform operator I WANT the behaviour behind a switch that is off by default SO
  THAT mctl-agents#992 can be rolled out in the agreed order and rolled back by
  configuration alone.

## Acceptance criteria (EARS)

Switch and startup
- THE SYSTEM SHALL read `MCTL_EXECUTION_REQUEST_QUEUE_WHILE_ACTIVE` once at startup.
  Empty or `off` means off and `on` means on. IF the value is anything else THEN the
  process SHALL refuse to start, in the same way as `MCTL_SUBMIT_CREATES_EXECUTION`.
- WHILE the switch is off THE SYSTEM SHALL keep create, claim, fulfil and reject exactly
  as today:
  - a create on an item with a Pending or Running execution returns 409
    `execution_active` and stores no row, event or idempotency record;
  - claim selects candidates as today;
  - the orphan reconciler does not run.

Queueing at create (switch on)
- WHEN a create arrives, the switch is on, and the only failing check is that the item
  has a Pending or Running execution, THE SYSTEM SHALL do all of the following:
  - insert a `pending` request with the caller's `requested_by`, principal ids, surface,
    `intent_id`, `resumed_from_execution_id`, `expected_state_version` and
    `idempotency_key`;
  - append an `execution_requested` event whose detail carries
    `queued_behind_execution_id`;
  - remember the idempotency key;
  - return 201 with the request.
- WHILE the switch is on THE SYSTEM SHALL keep every other create check and its error
  unchanged:
  - stale `expected_state_version`: 409 `state_version_conflict`;
  - terminal item: 409 `invalid_transition`;
  - a kind the item cannot take: 409 `invalid_transition` or 400;
  - unknown `resumed_from_execution_id`: 404 `execution_not_found`;
  - unknown or redacted intent: 404 `intent_not_found` or 409 `intent_unavailable`;
  - a second open request: 409 `execution_request_open`.
- WHEN the same actor repeats a queued create with the same idempotency key and body,
  whether the execution is still open or has since closed, THE SYSTEM SHALL return the
  original request (`created=false`, `replayed: true`) and SHALL NOT insert a second row.

Claim guard (switch on)
- WHILE the switch is on and a work item has a Pending or Running execution, THE SYSTEM
  SHALL NOT return any request of that item from `POST /execution-requests/claim`. This
  covers a `pending` request and a `claimed` request whose lease has lapsed.
- WHILE the switch is on THE SYSTEM SHALL apply the guard both when it selects candidates
  and again under the item's advisory lock before the compare-and-set. Blocked items
  therefore never use up the `claimCandidates` budget that other, unblocked items need.
- WHEN the blocking execution reaches a terminal phase (Succeeded, Failed or Error),
  whether the owning loop reported it or the orphan reconciler closed it, THE SYSTEM
  SHALL make the queued request claimable again with its stored fields unchanged.

Fulfil
- WHEN a queued request is fulfilled, THE SYSTEM SHALL still decide it with `resumeTx` or
  `checkStart`/`attachNewTx`, using the request's stored `expected_state_version`. IF the
  item's `state_version` changed after the request was stored THEN fulfil SHALL fail with
  409 `state_version_conflict` and SHALL NOT attach an execution.
- IF an execution is open at fulfil time (a race the claim guard narrows but cannot
  remove) THEN fulfil SHALL fail with 409 `execution_active`, as today, and the request
  SHALL stay `claimed`.

Orphan reconciliation (switch on, Temporal executions only)
- WHILE the switch is on THE SYSTEM SHALL periodically examine open executions with
  `engine=temporal` that have an open request queued behind them and that started at
  least the configured minimum age ago.
- WHEN Temporal reports the owning run as closed (Completed, Failed, Canceled, Terminated
  or TimedOut), or reports the run as not found, THE SYSTEM SHALL do the following under
  the item's lock, guarded by a compare-and-set on the phase:
  - move the execution to `Error` and set `ended_at`;
  - append an `execution_orphan_closed` event recording the Temporal status and the
    engine ref.
- IF Temporal reports the run as Running or ContinuedAsNew, the status is Unknown, or the
  describe call fails THEN THE SYSTEM SHALL leave the execution unchanged and log the
  reason. A run it cannot read is never treated as closed.
- THE SYSTEM SHALL NOT change the phase of an execution that is already terminal.

Real-API grant test
- WHEN the DevLoop's approve flip has decided the first `dev-loop` grant on a canonical
  `we_` that is still Running, THE SYSTEM SHALL do both of the following:
  - accept a second grant request on that same execution;
  - let `POST /api/v1/agents/dev-loop/{workflow_id}/approve` decide the newest grant.

  This is verified by `TestDevLoopApprove_SecondGrantOnOpenExecutionAfterFlip` against
  real PostgreSQL.

Documentation
- THE SYSTEM SHALL update the following to describe the switch-on behaviour and to state
  that switch-off behaviour is unchanged:
  - `internal/openapi/openapi.yaml`;
  - `docs/work-context-contract.md`;
  - the `mctl_request_work_item_execution` tool text in `internal/mcp/workitems.go`;
  - a new ADR.

## Out of scope

- What a resume delivered after implement closes means to the DevLoop: it must trigger a
  real continuation, not a silent no-op ending Succeeded (paired mctl-agents issue).
- Enabling the mctl-agents dispatcher (`EXECUTION_REQUEST_DISPATCHER`), Temporal replay,
  and the amended spec and approval digest for mctl-agents#991 and #992.
- Orphan reconciliation for `argo` and `a2a` executions. Those stay blocked until their
  owner closes them, or until mctl-agents#993 covers them.
- Turning the switch on in production. That is a separate mctl-gitops change, made after
  release.

## Open questions

- Phase mapping of the four outcomes. mctl-api has only three terminal phases
  (`Succeeded`, `Failed`, `Error`; `internal/workitems/types.go`). The proposal assumes
  that mctl-agents reports Cancel and Timeout as `Error` (or `Failed`). It tests every
  terminal phase, plus orphan closure for Temporal `Canceled`, `Terminated` and
  `TimedOut`. mctl-agents#992 must confirm the phases it actually posts.
- Stale versions. If the DevLoop transitions the work item (for example to `waiting`)
  after a request was queued, every request queued during implement fails at fulfil with
  `state_version_conflict`. That is the required "stale handling", but it may make
  queueing useless for resume. Whether the DevLoop bumps `state_version` during or after
  implement belongs to the paired mctl-agents issue.
- ADR location. mctl-api has no `docs/adr/` directory; existing ADRs (010, 011, 020) live
  in `mctlhq/mctl-agents`. The proposal adds `docs/adr/0001-queue-execution-request-while-active.md`
  in mctl-api. The reviewer may prefer an mctl-agents ADR number instead.
- Reconciler cadence and minimum age. The proposal uses a 2-minute tick and a 5-minute
  minimum age. Should these be configurable?
