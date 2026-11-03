# DevLoop deferred resume after implement, orphaned-execution recovery and gated rollout (pairs mctl-api#931)

## Context
mctl-agents#991 / PR #992 keeps the DevLoop's canonical `we_` open through the implement run so the implement
run token can bind to it. While a `we_` is non-terminal, mctl-api refuses every other execution request for the
item (409 `execution_active`). mctlhq/mctl-api#931 changes that: mctl-api will queue a request while an execution
is active and only let it be claimed once the execution closes. This proposal is the mctl-agents half. It defines
what such a deferred request does when it finally reaches the loop. Today `DevLoopWorkflow._deliver`
(`orchestrator/temporal/workflows/dev_loop.py`) sees `self._gates_passed` and lands the execution `Succeeded`
without doing any work. That is a silent no-op, and the issue's owner decisions (2026-11-03) rule it out.

The proposal also covers four more items. It adds recovery for a `we_` left open by a loop that was terminated
(today `Dispatcher._reconcile_closed_loops` runs only when a request is claimed, so nothing can unblock the item).
It gates the rollout order (mctl-api queue switch, then `IMPLEMENT_EXECUTION_PATCH`, then worker image bump) on a
detectable mctl-api capability. It specifies the tests that must exist before the 21 failing #992 resume tests are
rewritten. It covers the spec and ADR amendments that need a fresh approval digest.

## User stories
- AS a reviewer giving feedback through a surface while the implementer runs I WANT my request delivered to
  the PR's shepherd once implement ends SO THAT my feedback is acted on and not silently marked done.
- AS an approver I WANT any request that would add new work or change the approved content to stop for a fresh
  human approval SO THAT the original approval is never used as authority for new work.
- AS a surface user I WANT a typed refusal (for example `work-merged`) when there is nothing left to resume
  SO THAT I know my request was not executed and can file a new WorkItem.
- AS an operator I WANT a `we_` left open by a terminated loop to be ended automatically SO THAT queued
  requests for that item are not blocked forever.
- AS a release owner I WANT the worker to hold the canonical `we_` through implement only when mctl-api
  queues requests SO THAT rolling the worker image ahead of mctl-api cannot drop requests.

## Acceptance criteria (EARS)

Delivery identity
- WHEN the dispatcher delivers an execution request THE SYSTEM SHALL carry its `execution_request_id`,
  `work_item_id`, `surface`, actor, `kind`, `intent_id`, `expected_state_version` and
  `resumed_from_execution_id` in `ResumeDelivery`. Every new field SHALL be defaulted, so `ResumeDelivery`
  payloads recorded before this change still decode.
- WHEN the same request is delivered again (re-claim, Temporal update retry, continue-as-new or replay)
  THE SYSTEM SHALL run at most one feedback tick for that `execution_request_id`.

Deferred-resume contract (applies only to loops that record the new `DEFERRED_RESUME_PATCH` marker)
- WHILE the implement step of a loop under the new contract is in flight, THE SYSTEM SHALL answer a delivered
  `resume` with `ResumeDeferred` (`implement-running`) and SHALL NOT accept it.
- WHEN a `resume` with an `intent_id` is delivered to a loop that is in its merge watch with the PR open
  THE SYSTEM SHALL accept it, bind its `we_`, and schedule exactly one shepherd feedback tick for this proposal.
  That tick SHALL carry the `intent_id`, `execution_request_id` and actor.
- WHEN the feedback tick runs THE SYSTEM SHALL first decide scope against the approved proposal. In-scope
  feedback SHALL be processed through the shepherd review-feedback path. New requirements, changed authority or
  a material scope expansion SHALL NOT be implemented, and SHALL return the outcome `scope-expansion`.
- IF the approval grant's binding (approval ref, approved content digest, approval authority) is no longer
  valid when the feedback tick is about to run THEN THE SYSTEM SHALL NOT run the tick, and SHALL end the
  delivery with the typed refusal `reapproval-required`.
- WHEN the feedback tick confirms that feedback processing happened (a review-feedback commit was pushed, or the
  shepherd reports the feedback as already addressed with evidence) THE SYSTEM SHALL end the delivery's `we_`
  `Succeeded`.
- IF the feedback tick fails, is refused, times out or reports an unobservable outcome THEN THE SYSTEM SHALL end
  the delivery's `we_` `Failed` and record a typed `ResumeRejection` reason (`feedback-failed`,
  `feedback-unobservable`, `scope-expansion`, `reapproval-required`). It SHALL NOT end it `Succeeded`.
- IF the merge watch ends before an accepted delivery's feedback tick runs THEN THE SYSTEM SHALL end its `we_`
  `Failed` with `work-merged` (PR merged) or `feedback-not-run` (PR closed or watch deadline).
- IF the fulfil of a deferred request is refused with `state_version_conflict` (stale `expected_state_version`)
  THEN THE SYSTEM SHALL reject the request and SHALL NOT run a feedback tick for it.
- IF a `resume` is delivered after the loop has observed its PR merged THEN THE SYSTEM SHALL refuse it with
  `ResumeRefused` and the reason `work-merged` before any `we_` is minted, so the intent stays on the request row.
- IF a `resume` with no `intent_id` is delivered to a loop whose gates are already passed THEN THE SYSTEM SHALL
  refuse it with `ResumeRefused` and the reason `nothing-to-resume`, and SHALL NOT end anything `Succeeded`.
- WHILE a feedback tick for a delivery runs THE SYSTEM SHALL keep PR/head ownership fencing (lifecycle claim,
  `--match-head-commit`), the independent review gate and CI gates exactly as for a scheduled tick.
- WHEN a `resume` with an intent is delivered after the implement step ended Failed, Cancelled or TimedOut (the
  loop has closed) THE SYSTEM SHALL take the existing closed-loop path (Update-with-Start of a new run). The
  investigator SHALL rewind an `accepted` or `needs-triage` proposal that has no open PR to `proposed`, using the
  pinned intent. The new run SHALL wait for a fresh human approval before any implementer is released.
- IF the proposal has an open or merged PR THEN THE SYSTEM SHALL NOT rewind it to `proposed`.

Backward compatibility
- WHILE replaying a history recorded without `DEFERRED_RESUME_PATCH` THE SYSTEM SHALL keep the old command
  sequence, including landing `Succeeded` at once when `_gates_passed` is true.

Orphaned-execution recovery
- WHEN a DevLoop run that owns a non-terminal `we_` (its canonical `<loop>#run_<run id>` or a delivery's
  `<loop>#xr_<id>`) is CLOSED or ABSENT in Temporal THE SYSTEM SHALL end that execution `Failed`. This SHALL work
  without any claimable request, within one orphan-sweep interval.
- WHILE the owning run is RUNNING and holds the execution THE SYSTEM SHALL NOT touch it.
- IF a Temporal or mctl-api read in the sweep fails THEN THE SYSTEM SHALL skip that execution, and SHALL NOT
  treat the failure as "loop gone".
- WHERE `EXECUTION_ORPHAN_SWEEP_SECONDS` is 0 THE SYSTEM SHALL disable the sweep, leaving the claim-time
  reconciliation unchanged.

Rollout gating
- WHEN the loop reaches the approve-flip decision point THE SYSTEM SHALL hold the canonical `we_` through
  implement only if an activity reports that mctl-api has the queue-while-active capability enabled. That answer
  is recorded in history. Otherwise the loop SHALL end the `we_` at the flip as before.
- IF the capability probe cannot get an answer THEN THE SYSTEM SHALL treat the capability as off (fail closed
  to today's behaviour).
- WHEN an operator prepares the worker image bump THE SYSTEM SHALL provide a read-only check that reports
  whether mctl-api's queue switch is on.

Tests and documents
- WHEN this change is merged THE SYSTEM SHALL have mutation-discriminating regression tests and end-to-end tests
  for the new contract. These tests SHALL be committed before any existing expectation is rewritten.
- WHEN the change is merged THE SYSTEM SHALL contain an ADR for the deferred-resume contract, the amended #991
  requirements/design/tasks, and corrected `_await_canonical_reapproval` and `_launch_correlation` docstrings.

## Out of scope
- The mctl-api half: the queue while active, the claim guard and the switch (mctlhq/mctl-api#931).
- Retrying a pending canonical end-advance during the merge watch (owner decision 5). That is tracked with
  #991 / PR #992 and only referenced here.
- Changing the gitops `EXECUTION_REQUEST_DISPATCHER` value. It is already `"true"` in
  `services/admins/mctl-agents-worker/values.yaml:139`.
- Any automatic approval of an amendment or a new WorkItem raised by `scope-expansion`.
- Holding the approve flip for a request queued before it (an open owner question, see below).

## Open questions
- Whether a request queued before the approve flip should hold the flip. This proposal does not hold it. A
  request queued then is delivered after implement and follows the contract above.
- Where argo/a2a orphan reconciliation lives, and whether the work-item API can list open executions without a
  request. Assumed: mctl-api#931 adds a list endpoint for non-terminal `temporal` executions. Until then the
  sweep uses Temporal visibility. The issue says the owner has not decided this.
- How to detect that mctl-api has the queue switch on. Assumed: a capability flag readable by the worker
  identity. The field name and endpoint must come from #931.
- Who bumps the worker image. Assumed: a human release owner, after the read-only check passes. The image is no
  longer bumped by an automated bump.
- How the shepherd reports "meaningful feedback processing confirmed". Assumed: a new structured result from
  `run_shepherd` (the CWFT output parameter `feedback_outcome`). This needs a gitops change to the shepherd CWFT
  (`intent_id` / `execution_request_id` params and the output). That change is not visible from this clone.
- The idempotency key the surface sent is not on `ExecutionRequest`
  (`orchestrator/work_context/execution_requests.py`), so the loop cannot see it. The proposal uses
  `execution_request_id` as the idempotency identity, because mctl-api maps one idempotency key to one request.
