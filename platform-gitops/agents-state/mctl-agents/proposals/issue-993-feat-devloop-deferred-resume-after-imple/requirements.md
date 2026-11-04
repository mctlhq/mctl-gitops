# DevLoop deferred resume after implement, orphaned-execution recovery and gated rollout (pairs mctl-api#931)

## Amendment 2026-11-03
This amendment supersedes the version posted on 2026-11-03 (status `proposed`, never approved). It needs a fresh,
digest-bound human approval; the earlier grant must not be used. What changed and why (owner decisions on
mctl-agents#993, 2026-11-03: path A, the disposition with items 1-7, and the review of gitops#2377):
- Path A. mctl-agents#991 stays `implemented`, and its proposal is not touched. The changes that were drafted for it
  (mctlhq/mctl-gitops#2375, closed without merge) move here: the merge-watch retry of a pending canonical
  end-advance (now IN scope, was "out of scope, tracked with #991"), the corrected facts about how the loop ends
  the `we_`, the stale docstrings, the replay fixtures and the rollout gate. This proposal asks for no change to the
  #991 proposal and no new #991 digest.
- Delivery. The code this proposal changes exists in two places: `main`, and the open draft PR mctl-agents#992
  (`IMPLEMENT_EXECUTION_PATCH`, the hold of the canonical `we_`, which exist only on #992's branch). The
  implementer cannot stack on another PR's branch (it clones the default branch and opens the PR against `main`).
  The work is therefore split into Part M (lands on `main` through this proposal's implementer) and Part S (lands
  as commits on #992's existing branch, by an operator-directed session under this proposal's approved digest, because the shepherd cannot). See "Delivery and rollout order".
- Rollout switch. The earlier text assumed the worker could learn from mctl-api that its queue switch is on. The
  accepted mctl-api#931 proposal adds no capability endpoint or field (only `queued_behind_execution_id` on a
  successful create), so that assumption is removed. The hold is gated by an explicit worker switch, off by default,
  that a human release owner turns on only after a functional check of mctl-api (below). A patch marker cannot be a
  rollout switch: `workflow.patched` is true for every new execution as soon as the code ships.
- Orphan sweep. The earlier text assumed #931 adds a list endpoint for open executions. It does not, and #931 is not
  to be amended for it. The sweep is rebuilt on sources confirmed in code: Temporal visibility plus the loop's own
  `work_context` query, narrow to `temporal`, with a starvation-proof cursor, a spike that gates it, and a typed
  blocker if the spike fails. argo and a2a are out of scope and tracked separately.
- Guarded reinvestigation. Moving a Failed/Cancelled/TimedOut loop's proposal to `proposed` requires positive proof of no live writer, PR,
  pushed branch, or unresolved owner. Uncertainty means `needs-triage` and no new implementer.
- Rollout order. `#931 switch ON -> old worker -> new worker` is not automatically safe. The order is now: inert
  deferred-resume handling first, a legacy-loop fence, then the mctl-api switch, then the hold.
- Corrected facts (carried from the closed #2375): the loop only ever writes `Succeeded` or `Failed` to a `we_`,
  never `Error` (only mctl-api's #931 sweeper writes `Error`). Under #992 a failed, cancelled or timed-out implement
  raises out of `_implement` and `run()`'s exception path ends the `we_` `Failed`; the
  `Succeeded if implement_result.succeeded else Failed` line after `_implement` is reachable only on success.
  `after_flip` is False under the hold marker and is kept only for the legacy `resume` signal. The dispatcher is
  already ON in production (`platform-gitops/services/admins/mctl-agents-worker/values.yaml:139`, commit f1fc08233,
  2026-09-24), so it is not a rollout step.
- New verified fact: a continue-as-new hop of the merge watch drops the pending end-advance entirely (see the retry
  requirement). That is a defect on #992's branch, fixed by Part S.

## Context
mctl-agents#991 / PR #992 keeps the DevLoop's canonical `we_` open through the implement run so the implement
run token can bind to it. While a `we_` is non-terminal, mctl-api refuses every other execution request for the
item (409 `execution_active`). mctlhq/mctl-api#931 changes that behind a switch that is off by default: mctl-api
will queue a request while an execution is active and only let it be claimed once the execution closes. This
proposal is the mctl-agents half. It defines what such a deferred request does when it finally reaches the loop.
Today `DevLoopWorkflow._deliver` (`orchestrator/temporal/workflows/dev_loop.py`) sees `self._gates_passed` and
lands the execution `Succeeded` without doing any work. That is a silent no-op, and the issue's owner decisions
(2026-11-03) rule it out. This no-op also exists on `main` today, for a resume that reaches a loop in its merge
watch, because the dispatcher is already on.

The proposal also covers: the merge-watch retry of a pending canonical end-advance; recovery for a `we_` left open by
a terminated loop; an explicit worker switch for the hold with a functional operator check of mctl-api; the tests
that must exist before the 21 failing #992 resume tests are rewritten; and the ADR and docstring fixes.

## User stories
- AS a reviewer giving feedback through a surface while the implementer runs I WANT my request delivered to
  the PR's shepherd once implement ends SO THAT my feedback is acted on and not silently marked done.
- AS an approver I WANT any request that would add new work or change the approved content to stop for a fresh
  human approval SO THAT the original approval is never used as authority for new work.
- AS a surface user I WANT a typed refusal (for example `work_merged`) when there is nothing left to resume
  SO THAT I know my request was not executed and can file a new WorkItem.
- AS an operator I WANT a `we_` that the loop failed to end, or that a terminated loop left open, to be ended
  SO THAT queued requests for that item are not blocked for up to 14 days.
- AS a release owner I WANT the worker to hold the canonical `we_` through implement only after I have proved
  with a functional check that mctl-api queues requests, and only when I switch it on SO THAT rolling out the
  worker image ahead of mctl-api cannot drop requests.

## Acceptance criteria (EARS)

Delivery identity (Part M)
- WHEN the dispatcher delivers an execution request THE SYSTEM SHALL carry its `execution_request_id`,
  `work_item_id`, `surface`, actor, `kind`, `intent_id`, `expected_state_version` and
  `resumed_from_execution_id` in `ResumeDelivery`. Every new field SHALL be defaulted, so `ResumeDelivery`
  payloads recorded before this change still decode.
- WHEN the same request is delivered again (re-claim, Temporal update retry, continue-as-new or replay)
  THE SYSTEM SHALL run at most one feedback tick for that `execution_request_id`.

Deferred-resume contract (Part M; applies only to loops that record the new `DEFERRED_RESUME_PATCH` marker)
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
  `Failed` with `work_merged` (PR merged) or `feedback-not-run` (PR closed or watch deadline).
- IF the fulfil of a deferred request is refused with `state_version_conflict` (stale `expected_state_version`)
  THEN THE SYSTEM SHALL reject the request and SHALL NOT run a feedback tick for it.
- IF a `resume` is delivered after the loop has observed its PR merged THEN THE SYSTEM SHALL refuse it with the typed
  outcome `ResumeRefused(work_merged)` before any `we_` is minted. The request row keeps the original `intent_id`,
  actor, surface, `request_id`, `expected_state_version`, `resumed_from` and idempotency identity unchanged. THE SYSTEM
  SHALL NOT end anything `Succeeded`, SHALL NOT create an issue or WorkItem automatically, and SHALL NOT reopen,
  push to or otherwise act on the merged PR. Further work on a merged change is a new WorkItem started by a human
  (owner decision 2, 2026-11-04).
- WHEN the loop has already ended (merge watch finished, PR merged, loop closed) a later resume takes the closed-loop
  path, where the Update-with-Start validator cannot make a GitHub read. THE SYSTEM SHALL then refuse in the dispatcher,
  before the fulfil, using the tri-state PR read: a merged PR is `ResumeRefused(work_merged)` and a request without
  intent is `ResumeRefused(no_actionable_intent)`; no `we_` is minted. A failed or `unknown` read defers the request
  (it stays claimed), and neither refuses nor delivers it.
- IF a `resume` with no `intent_id` is delivered to a loop whose gates are already passed THEN THE SYSTEM SHALL
  refuse it with the typed outcome `ResumeRefused(no_actionable_intent)` and SHALL NOT end anything `Succeeded`. The
  request keeps its identity (actor, surface, `request_id`, idempotency) and the refusal reason is persisted on the
  request row, which is the record the originating surface reads, so the surface can show why nothing happened. The
  task verifies that read path for each surface that can send a resume; a surface that cannot read it is recorded as
  a blocker, never papered over with a success (owner decision 4, 2026-11-04).
- WHILE a feedback tick for a delivery runs THE SYSTEM SHALL keep PR/head ownership fencing (lifecycle claim,
  `--match-head-commit`), the independent review gate and CI gates exactly as for a scheduled tick.
- WHEN a request was queued before the approve flip THE SYSTEM SHALL NOT hold the flip because of it. After the
  current execution ends it SHALL follow the same checked contract, and new scope or an authority change SHALL
  require a fresh human approval (owner decision 5, 2026-11-03).

Closed-loop path after a failed implement (Part M): guarded reinvestigation (owner decision 3, 2026-11-04)
- WHEN a `resume` with an intent is delivered after the implement step ended Failed, Cancelled or TimedOut (the
  loop has closed) THE SYSTEM SHALL take the existing closed-loop path (Update-with-Start of a new run). mctl-api
  cannot tell the three apart, and none of them is by itself proof that the prior execution stopped: a timeout in
  particular only means the caller stopped waiting.
- THE SYSTEM SHALL move an `accepted` or `needs-triage` proposal to `proposed` with the pinned intent ONLY when ALL of
  these are positively established, each by a successful read:
  (a) the prior execution is terminal (its `we_` and its implement Workflow are closed, not merely timed out);
  (b) no implementer is active: no live implement Workflow for the slug and no live attempt lease;
  (c) no lifecycle-ownership claim for the proposal is active, and no lifecycle owner remains;
  (d) no open PR is being handled: `.status.yaml` carries no PR, and GitHub shows no open `feat/agents-<slug>` PR;
  (e) outstanding side effects are reconciled: no merged `feat/agents-<slug>` PR, no pushed `feat/agents-<slug>`
      branch, and no other unsettled execution request for the work item (the request being processed is excluded
      by `request_id`, otherwise it would refute the check forever). A pending end-advance exists only inside a
      running workflow; on a closed run it can be read only through the `work_context` query proven by spike task 10.
      Until that spike passes it is `unknown` and blocks.
  Readable sources, using existing code only: the `we_` phase through `list_executions`; ownership through
  `OwnershipClient.get` (verdicts `UNKNOWN` / `UNOWNED`, and the PR-kind phase when a PR exists); the attempt lease
  through `attempt_expires_at` of `list_proposal_refs` (an expired lease is not proof of death, so (b) also needs the
  Temporal visibility read of live implement Workflows); and NEW tri-state reads for the PR state by branch and for
  branch existence. `find_pr_for_proposal` returns `None` on a failed `gh` call, malformed JSON or a missing body
  marker, so it must not be used for these checks: a failed read is `unknown`, never `no PR`.
- Each check has exactly one of three results: `proven` (the safe condition is established by a successful read),
  `refuted` (a successful read shows the unsafe condition: a live implementer, a live owner, an open PR, a pushed
  branch, a pending side effect) or `unknown` (the read failed, was partial or malformed, or the result is only
  inferred). Only all-`proven` permits `proposed`. A `refuted` or `unknown` result on any check blocks it; neither
  is ever treated as absent. A merged PR is the one refuted case with its own outcome, `ResumeRefused(work_merged)`
  above, and it is checked first.
- IF any of (a) to (e) is `refuted` or `unknown`, or ownership or side effects are uncertain, or a result is only
  inferred from a timeout, THEN THE SYSTEM SHALL write `needs-triage` with a typed evidence record naming each check
  and its result (`proven`, `refuted` or `unknown`), SHALL NOT move the proposal to `proposed`, and SHALL NOT release
  an implementer, so a duplicate implementation can never start.
- BEFORE writing `proposed` THE SYSTEM SHALL take the proposal's lifecycle ownership (or compare-and-swap on the
  `.status.yaml` content SHA read with the checks), so the stranded-accepted scan of `ImplementSweepWorkflow` cannot
  start an implementer between the checks and the write. The `needs-triage` or `proposed` write and the intent
  binding are one transition; a redelivery after a partial write re-reads everything and converges to the same state,
  and a lost race writes nothing. The `needs-triage` write lives in the `run_shepherd` path, which owns every such
  write.
- THE SYSTEM SHALL bind the preserved intent (`intent_id`, actor, surface, `request_id`, idempotency) to the new
  investigation, and SHALL NOT reuse, rewrite or extend an earlier digest-bound approval. The new run SHALL wait for a
  fresh human approval bound to the then-current content digest before any implementation.
- IF the proposal has an open PR, or a merged one, THEN THE SYSTEM SHALL NOT move it to `proposed`; a merged PR is
  `ResumeRefused(work_merged)` above.

Cross-branch invariants (merged, no intent, failed/cancelled/timed out)
- Every branch preserves actor, surface, `intent_id`, `request_id` and the idempotency key from the dispatcher through
  the validator, the delivery and the persisted outcome; a redelivery or replay of the same request yields the same
  terminal outcome and creates no second effect.
- The terminal outcomes of a resume REQUEST are a closed, stable vocabulary: `ResumeRefused(work_merged)`,
  `ResumeRefused(no_actionable_intent)`, the existing refusals and deferrals of the validator, and the request being
  delivered. `work_merged` is also the `Failed` reason of a `we_` whose merge watch ended before its feedback tick;
  that is a reason on the execution, not a request outcome. `needs-triage` and `proposed` are states of the PROPOSAL (the investigation), not terminal outcomes of
  the request: the request that triggered the closed-loop path is delivered, and the proposal's state then says
  whether the investigation may proceed. New values are added behind `DEFERRED_RESUME_PATCH`; recorded histories keep
  their old command sequence.
- The M1 slice (#996, implemented, PR not yet merged) persisted the hyphenated spellings `work-merged` and
  `nothing-to-resume`. The stable wire values of this contract are `work_merged` and `no_actionable_intent`. Before
  the M1 PR merges, the spellings are aligned in that PR (mctl-agents#998) with the hyphenated spellings kept as read-side aliases; after any merge a
  rename needs a compatibility alias so persisted rows keep decoding.
- Persisted compatibility: every writer, test, document and serialised outcome uses the canonical values. A reader
  still decodes the hyphenated spellings if a stored row or recorded history already carries one, reads them back as
  written, and never rewrites or renames a historical result silently. The hyphenated spellings are never minted
  again. A test proves a legacy spelling decodes unchanged and is not normalised to `unspecified`.

Backward compatibility and fence (Part M)
- WHILE replaying a history recorded without `DEFERRED_RESUME_PATCH` THE SYSTEM SHALL keep the old command
  sequence.
- WHEN a `resume` is delivered to a RUNNING loop whose gates are passed and that did not record
  `DEFERRED_RESUME_PATCH` THE SYSTEM SHALL answer `ResumeDeferred` (`legacy-loop`) instead of landing `Succeeded`.
  Such a loop keeps `legacy-loop` for its whole life, because the flag is carried in `MergeWatchResume` and never
  re-evaluated (a mid-flight legacy loop lacks the state the contract needs); it leaves that state only by ending.
  The request stays claimable meanwhile. The Update validator records no command, so this changes no history.
- WHEN an operator asks for the contract state of running loops THE SYSTEM SHALL list every RUNNING DevLoop run
  with gates passed and without the contract (a read-only command), so the drain can be proven before the
  mctl-api switch is turned on.

Inert staging (Part M)
- WHERE the worker switch `DEVLOOP_DEFERRED_FEEDBACK` is not explicitly on THE SYSTEM SHALL NOT run a feedback
  tick. WHEN a resume with an intent is accepted by a contract loop with the PR open and the switch is off, THE SYSTEM
  SHALL end the delivery's `we_` `Failed` with the typed rejection `feedback-disabled`. The answer is read through
  an activity and recorded in history. A read that gets no answer counts as off.

Retry of a pending canonical end-advance (Part S; on PR #992's branch)
- WHEN `_implement` returns under the hold marker THE SYSTEM SHALL end the canonical execution once, `Succeeded`,
  before the abandon check and the merge watch.
- IF `_implement` raises (a failed, cancelled or timed-out implement run, or a non-retryable error) THEN THE SYSTEM
  SHALL end the canonical execution `Failed` from `run`'s exception path, and SHALL NOT end it from the line after
  `_implement`. THE SYSTEM SHALL only ever write `Succeeded` or `Failed` to the `we_`; `Error` belongs to mctl-api's
  orphan sweeper (mctlhq/mctl-api#931).
- IF the post-implement end-advance does not land (the `we_` is still open and `_canonical_pending_phase` is set)
  THEN THE SYSTEM SHALL retry it once per merge-watch poll, under its own marker `IMPLEMENT_END_RETRY_PATCH`
  ("implement-end-retry"), with `FAST_ACTIVITY_RETRY_POLICY`, and SHALL stop as soon as it lands. The retry
  interval is the watch cadence, so an open `we_` cannot block a queued request for the 14-day watch.
- WHILE the merge watch hops via continue-as-new THE SYSTEM SHALL make one last attempt before the hop and, if the
  `we_` is still open, carry its identity, open flag, pending phase and the retry flag into the continued run
  through defaulted `MergeWatchResume` fields. The continued run SHALL rehydrate them before its first await and
  keep retrying. (Today the continued run rehydrates none of them, so a pending end is dropped at the first hop.)
- WHILE a history records `IMPLEMENT_EXECUTION_PATCH` but not `IMPLEMENT_END_RETRY_PATCH`, THE SYSTEM SHALL replay
  it with no retry command in the merge watch.
- WHILE the hold marker is recorded, THE SYSTEM SHALL bind the re-approval gate between the flip and the implement
  submit with `after_flip=False` (grant on the canonical `we_`, `execution_id=""`). `after_flip=True` is kept only
  for histories without the hold and for the legacy `resume` signal (no sender in production).

Rollout switch for the hold (Part S, switch also read by Part M's activity)
- WHEN the loop reaches the approve-flip decision point under the hold marker THE SYSTEM SHALL hold the canonical
  `we_` through implement only if the activity `read_rollout_switches` reports `implement_hold` on. The answer is
  recorded in history, so replay is deterministic. Otherwise the loop SHALL end the `we_` at the flip as before and
  SHALL NOT pass `execution_id` to the implement run.
- IF the switch read gets no answer, or the value is not an explicit on, THEN THE SYSTEM SHALL treat the hold as off
  (fail closed to today's behaviour).
- WHILE a history records `IMPLEMENT_EXECUTION_PATCH` but not the switch marker THE SYSTEM SHALL replay it as a
  held `we_` (the behaviour that history recorded).
- THE SYSTEM SHALL NOT infer the state of mctl-api from the worker. The switch is turned on by a human release owner,
  in mctl-gitops, only after the functional check in "Delivery and rollout order" has passed.

Orphaned-execution recovery (Part M; Temporal only)
- WHEN a DevLoop run that owns a non-terminal `we_` (its canonical `<loop>#run_<run id>` or a delivery's
  `<loop>#xr_<id>`) is CLOSED or ABSENT in Temporal THE SYSTEM SHALL end that execution `Failed`, without any
  claimable request, within one full pass of the sweep.
- THE SYSTEM SHALL find candidates only from sources confirmed in code: Temporal visibility (closed DevLoop runs)
  and the run's own `work_context` query. THE SYSTEM SHALL confirm every candidate with a read of the work item
  from mctl-api before writing. THE SYSTEM SHALL NOT assume a list endpoint of open executions.
- WHILE the owning loop is RUNNING and holds the execution THE SYSTEM SHALL NOT touch it. A run that continued as new
  is not closed.
- IF any Temporal or mctl-api read fails, is partial or malformed (including a page that fails after earlier
  pages succeeded, a query on a closed run that cannot be replayed, or a non-conclusive describe) THEN THE SYSTEM
  SHALL skip that execution, count it as unobserved, and SHALL NOT treat the failure as "loop gone" or "nothing
  open". A cycle whose listing failed SHALL NOT advance its cursor.
- THE SYSTEM SHALL examine at most a fixed batch of closed runs per cycle, and SHALL rotate through all closed runs
  within the namespace retention with a cursor, so that rows that stay unresolvable cannot starve later rows. New
  closes SHALL be examined by a separate fresh lane in the next cycle.
- THE SYSTEM SHALL write the end with a compare-and-set on the phase. mctl-api never changes the phase of a
  finished execution, so a second writer (the mctl-api#931 sweeper) or a repeated pass is a no-op that SHALL be
  treated as converged, not as a failure.
- THE SYSTEM SHALL NOT touch an execution of engine `argo` or `a2a`, and SHALL NOT touch an execution whose engine
  ref is not this dispatcher's own (`#xr_` or `#run_`).
- WHERE `EXECUTION_ORPHAN_SWEEP_SECONDS` is 0 (the default until the spike task passes) THE SYSTEM SHALL disable the
  sweep, leaving the claim-time reconciliation unchanged.

Observability of mismatched states (Part M; see the matrix in design.md)
The property: an API that accepts a queued request while the worker cannot process it is never silent, and a request
is never ended `Succeeded` unless its feedback was processed.
- WHEN a worker starts THE SYSTEM SHALL log one line `ROLLOUT_STATE` with the effective `DEVLOOP_DEFERRED_FEEDBACK`,
  `DEVLOOP_IMPLEMENT_HOLD` (once Part S is present), `EXECUTION_REQUEST_DISPATCHER`, `EXECUTION_ORPHAN_SWEEP_SECONDS`,
  the dispatcher interval, the image/contract version, and `parse_errors` for any value that was set but not
  recognised. THE SYSTEM SHALL repeat the line at most every 5 minutes while the dispatcher runs, so a paused or stuck
  dispatcher is visible as a missing line.
- THE SYSTEM SHALL log the age of each request at `claim` and at `defer`, and a rate-limited `defer` line for
  `legacy-loop`, `implement-running` and `feedback-disabled`, so a request that is not progressing is visible with its reason.
- THE SYSTEM SHALL provide a read-only command `orchestrator/temporal/cli.py rollout-status` that, from confirmed
  reads only (Temporal visibility and the `contract_state`/`work_context` queries of RUNNING DevLoop runs, and the
  existing `GET /api/v1/work-items/{id}/execution-requests` for the items those runs name), prints: loops without the
  contract; loops holding a `we_` open with its age and any open (`pending`/`claimed`) requests with their `created_at`
  age; the recorded `ResumeRejection` reasons; and every read it could not make. A read it could not make SHALL be
  printed as UNKNOWN, never as zero.
- THE SYSTEM SHALL treat a documented observation window after each rollout step as a gate: no open request whose item
  has NO open execution older than 2x the dispatcher interval (30 s at the default 15 s) plus its lease; no open request
  behind a held `we_` older than the implement timeout plus 2x the interval; no unexpected 409 `execution_active` while a
  `we_` held by the hold switch is open (a repeat of the functional check on a fresh item while a held `we_` exists); no
  `defer` repeating for the same request for more than 3 lease periods.
- IF a state cannot be observed from confirmed reads (a request queued on an item that no running loop names, while the
  dispatcher is paused) THEN THE SYSTEM SHALL report it as UNKNOWN, never as zero, and SHALL NOT assume a capability. The aggregate read that would
  close this gap is mctlhq/mctl-api#933, tracked separately and not a dependency here (Decided item 6).

Tests and documents
- WHEN this change is merged THE SYSTEM SHALL have mutation-discriminating regression tests and end-to-end tests
  for the new contract, for BOTH states of each switch. These tests SHALL be committed before any existing
  expectation is rewritten.
- WHEN the change is merged THE SYSTEM SHALL contain an ADR for the deferred-resume contract, and corrected
  `_await_canonical_reapproval` and `_launch_correlation` docstrings (Part S).

## Delivery and rollout order

Parts
- Part M lands on `main` through this proposal's implementer: request identity, the contract marker, validators and
  the legacy-loop fence, the feedback tick (behind `DEVLOOP_DEFERRED_FEEDBACK`), the guarded reinvestigation, the orphan sweep,
  the shepherd outputs, the switch activity and its tests, and the ADR. None of it needs #992's code. The existing
  `main` test `test_a_resume_delivered_after_the_implement_step_succeeds_at_once` is rewritten here, after the
  behaviour and its mutation tests exist.
- Part S lands as commits on PR #992's existing branch (owner disposition 2: put changes in the existing branch,
  do not overwrite its owner): the `implement_hold` switch read at the flip site, `IMPLEMENT_END_RETRY_PATCH` and the
  hop-carried fields, the `after_flip` change, the two docstrings, the replay fixtures, the new tests for both switch
  states, and the rewrite of the 21 tests. This proposal specifies Part S; its implementer run SHALL NOT edit those
  files or tasks.
- WHO executes Part S, and under WHICH approval. Neither the shepherd nor `run_implementer --review-feedback` can:
  they act on findings of a non-draft PR under the #991 slug and its approval (verified, design.md "Part S authority").
  Part S is executed by an operator-directed session (a human, or a Claude session the owner starts explicitly) that
  pushes commits to #992's branch under THIS proposal's approved digest. The commits SHALL name the #993 approved
  content digest and the S-task ids. The session SHALL first verify that `.status.yaml` of #993 is `accepted` with a
  named approver and that the approved digest equals the current digest of the proposal directory.
- Single-writer rule for #992's branch. Before ANY push the session SHALL confirm that #992 is still a draft (the
  shepherd then only waits), that no shepherd or implement Workflow for the `issue-991-*` slug is running, and SHALL
  fetch and fast-forward or merge the remote head first; it SHALL push without force. A push that is rejected is
  re-fetched and re-examined, never forced. The PR stays draft throughout.
- Conflict risk and order. Part M (on `main`) and Part S (on #992's branch) both edit `dev_loop.py` (`ResumeDelivery`,
  `MergeWatchResume`, `_validate_execution_request`, `_deliver`, `_watch_pr`, `_carry_work_context`,
  `_resume_merge_watch`, the marker constants and `run`), the replay scenario registry and the worker's activity
  list. THEREFORE Part S SHALL NOT be pushed until Part M is merged AND released; #992's branch SHALL then be brought up
  to date by MERGING `main` INTO it (no rebase, no force-push), the marker and replay order re-checked, and the full
  suite and the replay of ALL fixtures (old and new) rerun green BEFORE the Part S commits are pushed. Part S is never
  merged or released before these integration gates, and #992 stays a draft through Part M and the Part S integration. Files likely to conflict:
  `orchestrator/temporal/workflows/dev_loop.py`, `orchestrator/temporal/worker.py` (activity registration),
  `tests/replay_scenarios.py`, `tests/test_workflow_replay.py`, `tests/test_dev_loop_workflow.py`,
  `tests/test_execution_request_replay.py`, `tests/test_execution_request_resume.py`,
  `tests/test_patch_memoization.py`, `tests/fixtures/histories/`, and `orchestrator/temporal/activities/rollout_switches.py`
  (created by Part M, extended by Part S).

Why not one stacked PR
- `run_implementer` clones the default branch (`_clone_target`, `gh repo clone ... --depth=10`,
  `orchestrator/run_implementer.py:1787-1794`), creates `feat/agents-<slug>` from it (`:4958-4959`), and opens the PR
  with `--base main` hard-coded (`:3784-3794`). There is no base option, so an implementer run cannot build on
  #992's branch and a PR it opens cannot target it. Adding a base option to the implementer is a separate change
  needing its own approval. Decided 2026-11-03: no base option; Part S is operator-directed.

Order (each step is a gate; nothing is marked ready, released or deployed before its gate)
1. Gitops (mctl-gitops PR): the shepherd CWFT declares the additive `intent_id`, `execution_request_id`,
   `feedback_actor` params and the `feedback_outcome` output. Additive; changes no behaviour.
2. Part M merged and released with `DEVLOOP_DEFERRED_FEEDBACK` off (inert). Set
   `EXECUTION_REQUEST_DISPATCHER` to `"false"` for the duration of the mixed-image roll, so a request cannot reach a
   pod that still runs the old image. The pause is REQUIRED, brief and deliberate (decided 2026-11-03): record its
   start and end, never leave it indefinite. After the roll, wait until every pod runs the new image
   (`mctl_get_service_pods` image tags and a `ROLLOUT_STATE` line from each pod). Resume the dispatcher (set it back to
   `"true"`) once the compatible image, the `legacy-loop` fence and the drain proof (step 3) hold, and BEFORE the mctl-api
   queue is enabled (step 5). After each of steps 2-7 hold the
   observation window of "Observability of mismatched states" before the next step.
3. Drain proof: the read-only contract-state command lists no RUNNING post-gates loop without the contract, or each
   listed loop has been drained or abandoned. The `legacy-loop` fence makes a straggler harmless meanwhile.
4. Turn `DEVLOOP_DEFERRED_FEEDBACK` on (gitops, human), once the CWFT output is live and the T-tests pass.
5. mctl-api: mctlhq/mctl-api#931 (PR #932) is released and `MCTL_EXECUTION_REQUEST_QUEUE_WHILE_ACTIVE=on` is set in
   gitops. A human verifies the effective state, below. This proposal does not turn the switch on.
6. Part S: after Part M is released, an operator-directed session merges `main` into the draft #992 branch and pushes the
   Part S commits (S0). #992 stays a draft until the integration evidence (full suite, every replay fixture, and the
   real observe exchange) exists; making it ready, merging and releasing it with `DEVLOOP_IMPLEMENT_HOLD` off is a later,
   explicit owner gate. With the switch off the behaviour equals today's: the `we_` ends at the flip and no
   `execution_id` is sent.
7. A human release owner sets `DEVLOOP_IMPLEMENT_HOLD=true` in `services/admins/mctl-agents-worker/values.yaml` (the
   main worker only; the exec and implement workers ignore it). Rollback is the same line set back to off.
The worker image bump is a human step; nothing here deploys autonomously.

Functional check of mctl-api (step 5; the evidence for step 7)
Use a throw-away WorkItem in a test tenant, with no GitHub issue ref (so the dispatcher can only reject its request,
with `no_runnable_target`, and never starts a loop):
1. `mctl_create_work_item` (tenant, title `queue-switch-check`) and `mctl_get_work_item` for `state_version`.
2. Attach an open execution of engine `argo` (not `temporal`, so no sweeper touches it): REST
   `POST /api/v1/work-items/{id}/executions` with `{"engine":"argo","engine_ref":"queue-switch-check-<n>","phase":"Running"}`
   (route `router.go:782`, handler `AttachWorkItemExecution`; there is no MCP tool for it).
3. `mctl_request_work_item_execution` with `kind=resume`, the `state_version`, and a fresh `idempotency_key`.
   Expected with the switch OFF: 409 `execution_active`, nothing stored. Expected ON: 201 with state `pending`
   and `queued_behind_execution_id` set. Anything else: INCONCLUSIVE, treated as OFF.
4. Repeat step 3 on fresh keys, at least 20 times, and read the replica set. A mixed 201/409 is a FAIL; a read that
   gives no answer is a FAIL (fails closed); a capability is never inferred from configuration alone. This is AGGREGATE
   evidence: it shows that the endpoint, as routed to the Service, answered 201 `pending` every time, not that each
   replica did. It is NOT per-replica proof and SHALL NOT be reported as such. What was checked (code and tooling)
   and why per-replica proof is not available: the mctl-api responses carry no replica identity (no served-by header or
   pod name in `internal/api`; `/readyz` reports dependency checks, not the queue switch, `router.go:320-350`);
   `mctl_get_service_pods`/`mctl_get_service_status` list pods, readiness, image and start time but cannot route a call
   to one pod; a pod-targeted authenticated call would need cluster-network access or a port-forward outside the MCP
   tools, which this proposal does not assume; and the mctl-api deployment is not in this repository's `services/`
   tree, so its replica count is not read here. Record, next to the 201 count: the pod list with Ready state, image and
   start time after the config change (every pod started after it), and the number of probes. A per-replica attestation
   becomes possible only with a replica identity in responses or an effective-config read, which would be an mctl-api
   change (not made here, see Decided item 3).
5. Cleanup, in this order: end the open execution (same POST with `"phase":"Succeeded"`); the dispatcher then
   claims the pending request and rejects it `no_runnable_target`; confirm with
   `mctl_list_work_item_execution_requests` that no request is left open; cancel the item.
The check is idempotent: every probe uses a fresh idempotency key, and a replayed key returns the original request
(`replayed: true`) rather than a second row. The worker never runs this check. Residual risk (aggregate evidence): a
replica that still has the switch off and is rarely routed to may not be sampled; it then answers a request with the
visible 409, as before, and never drops it silently. The observation windows after steps 5 and 7 re-run the probe.

## Out of scope
- The mctl-api half: the queue while active, the claim guard, the switch and its sweeper (mctlhq/mctl-api#931).
  This proposal asks for no change to #931 and adds no capability or list endpoint to it.
- The #991 proposal and its digest. They are not amended here.
- Orphan reconciliation for `argo` and `a2a` executions. Tracked separately in mctlhq/mctl-agents#995. The sweep here is
  `temporal` only.
- Changing the gitops `EXECUTION_REQUEST_DISPATCHER` value permanently. It is already `"true"` in
  `services/admins/mctl-agents-worker/values.yaml:139`; only the required, brief pause in step 2 is mentioned.
- Any automatic approval of an amendment or a new WorkItem raised by `scope-expansion`.
- Holding the approve flip for a request queued before it (decided: it does not hold).
- Turning the mctl-api switch on, releasing, or deploying. Those are separate human-gated steps.

## Decided (2026-11-03)
Owner review of gitops#2377 (comment 6612861915) decided the following; these are no longer open.
1. Part S is executed by an operator-directed Claude session on #992's existing branch, under this proposal's
   digest-bound approval, only after Part M is merged to `main` and released, with the single-writer checks. The
   implementer gets no base option (no scope expansion).
2. Branch integration is a merge of `main` into #992, never a rebase or force-push. #992 stays a draft through Part M and
   the Part S integration, with no shepherd competition; readiness, merge and release are a later explicit gate after
   the tests and the real observe exchange evidence. `implement-bash` stays bypass-open under #181 until independent
   production evidence.
3. No mctl-api capability field is added and #931 is not extended now. The hold uses the default-off
   `DEVLOOP_IMPLEMENT_HOLD`, an explicit operator gate, and the actual durable HTTP 201 `pending` check; an unknown read
   fails closed.
4. The dispatcher pause is required: brief and deliberate (`EXECUTION_REQUEST_DISPATCHER=false` during the mixed-image
   rollout), with start and end recorded, all worker pods and `ROLLOUT_STATE` verified, resumed after the compatible
   image, the `legacy-loop` fence and the drain, and BEFORE the API queue is enabled; never indefinite. A backlog on an
   item outside any running loop is unobservable with the current API: it is reported UNKNOWN, never zero.
5. The orphan sweep ships OFF (`EXECUTION_ORPHAN_SWEEP_SECONDS=0`) until spike C0 proves the closed-run `work_context`
   source and the end-to-end starvation tests pass. On failure it stays off with `ORPHAN_SOURCE_BLOCKED`; coverage is not
   faked. argo/a2a is a separately tracked gap: mctlhq/mctl-agents#995 (verified to exist, open).
6. A global queued-request read (bounded, tenant-scoped, read-only count and oldest age) is separate, tracked as
   mctlhq/mctl-api#933 (verified to exist, open). It is not a dependency of this proposal and not a change to #931. It
   should exist before unattended or long production operation; this rollout uses the bounded pause, item-scoped checks
   and explicit UNKNOWN.
7. Earlier resolved points: a request queued before the flip does not hold the flip (disposition item 5); the worker
   does not learn the mctl-api switch from the API; the work-item API has no complete paginated list of open executions
   (the sweep uses Temporal); a human release owner flips the worker image and switches.

Unknowns that a task must settle (the proposal does not assume an answer):
- How the shepherd reports "meaningful feedback processing confirmed": assumed a new structured result
  (`feedback_outcome`) from `run_shepherd`. The shepherd CWFT (`argo-workflows/cluster-templates/cwft-mctl-agents-shepherd.yaml`)
  is outside the paths visible to the authoring run, so whether it declares the params is unobserved.
- Whether a Temporal query on a TERMINATED DevLoop run returns `work_context` (spike task).
- Whether the Python SDK runs Update validators during replay (tests assert it does not change a replayed history).
- Whether the 21 #992 tests pass unchanged with the hold switch off (first task records the result).
- The Temporal namespace retention, which bounds the sweep's rotation.
- The idempotency key the surface sent is not on `ExecutionRequest`
  (`orchestrator/work_context/execution_requests.py`), so the loop cannot see it. The proposal uses
  `execution_request_id` as the idempotency identity, because mctl-api maps one idempotency key to one request.
