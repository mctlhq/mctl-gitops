# DevLoop M1: deferred-resume request identity, replay-safe contract marker and fail-closed validator fence

## Context
Issue mctlhq/mctl-agents#996 is slice M1 of the umbrella design mctlhq/mctl-agents#993. The umbrella's single implementation run failed, and the owner chose sequential DevLoop slices. M1 covers only the Part M substrate: #993 tasks 1-4 and tests T1-T4. The #993 digest `sha256:99be6a3d...fd79` is provenance only. This proposal needs its own digest and a fresh human approval.

Today, a `resume` execution request delivered onto a live DevLoop after the approval gates have passed (`DevLoopWorkflow._gates_passed`) is accepted by `_validate_execution_request`. `_deliver` then lands its execution `Succeeded` at once. The existing test `test_a_resume_delivered_after_the_implement_step_succeeds_at_once` pins this behaviour. When the request carries an intent and the implementation PR is open, that `Succeeded` is false: no shepherd feedback handling exists to act on the intent. M1 does four things:
- carries the request's identity onto the loop;
- records a replay-safe marker for the new contract;
- puts a typed, fail-closed fence on the validator;
- makes sure nothing reaches `Succeeded` without meaningful work, while the feedback slice (M2) is not installed.

## User stories
- AS a human resuming a DevLoop from a surface I WANT my resume refused or deferred with a typed reason when the loop cannot act on it SO THAT I never see a false `Succeeded`.
- AS the dispatcher I WANT the loop to receive the request's `intent_id`, `expected_state_version` and `resumed_from_execution_id` SO THAT a later slice can act on the exact intent and execution lineage.
- AS an operator I WANT old Temporal histories, old Update payloads and old continue-as-new records to replay and decode unchanged SO THAT deploying M1 cannot break in-flight loops.
- AS the owner I WANT the interim behaviour (no feedback slice) to be explicit and deterministic SO THAT I can merge M1 without enabling any feature.

## Acceptance criteria (EARS)
- WHEN `Dispatcher._dispatch` builds a `ResumeDelivery` THE SYSTEM SHALL copy `intent_id` (int or None), `expected_state_version` (int) and `resumed_from_execution_id` (str) from the `ExecutionRequest`. It SHALL keep `execution_request_id`, `work_item_id`, `surface`, `actor_kind`, `actor_id` and `kind` exactly as today.
- WHEN a `ResumeDelivery` payload recorded before M1 (without the three fields) is decoded THE SYSTEM SHALL decode it with `intent_id=None`, `expected_state_version=0` and `resumed_from_execution_id=""`.
- WHEN a run of `DevLoopWorkflow` sets `_gates_passed = True` in `run`, without replaying a history that lacks the marker, THE SYSTEM SHALL evaluate `workflow.patched(DEFERRED_RESUME_PATCH)` exactly once at that point and store the result in `self._deferred_resume_contract`.
- THE SYSTEM SHALL schedule no new activity, timer or child-workflow command under `DEFERRED_RESUME_PATCH`. The marker is the only command it adds.
- WHEN a merge watch continues as new THE SYSTEM SHALL carry `deferred_resume_contract` (default False) in `MergeWatchResume`. `_resume_merge_watch` SHALL restore it from that record and SHALL NOT re-evaluate the patch.
- WHILE `_gates_passed` is True AND `_deferred_resume_contract` is False (a legacy history) THE SYSTEM SHALL refuse a non-own `resume` delivery in the validator with `ResumeDeferred`, reason `legacy-loop`.
- WHILE `_deferred_resume_contract` is True AND `_gates_passed` is True, THE SYSTEM SHALL decide a non-own `resume` delivery in the validator, before any history event or fulfil, in this order:
  1. implement step submitted and not ended (`_implement_state.stage == "implementer"` and `outcome is None`): `ResumeDeferred`, reason `implement-running`;
  2. last observed PR merged: `ResumeRefused`, reason `work-merged`;
  3. `intent_id is None`: `ResumeRefused`, reason `nothing-to-resume` (there is no request to act on, so the refusal loses nothing);
  4. implement ended without success, or PR closed unmerged: `ResumeDeferred`, reason `recovery-not-ready`. A valid intent is never refused irreversibly here: #993 routes it through a controlled recovery (and a fresh approval where required) that slice M3 implements, and a PR closed without merge may be reopened;
  5. anything else (an intent with an open or not-yet-observed PR): `ResumeDeferred`, reason `feedback-not-ready`.
- IF the validator refuses or defers a delivery THEN THE SYSTEM SHALL write no history event. The dispatcher SHALL NOT call fulfil, so no `we_` is minted.
- WHEN the dispatcher receives `ResumeRefused` with `work-merged` or `nothing-to-resume` THE SYSTEM SHALL reject the request `resume_refused:<reason>`, with both reasons in `xr.RESUME_REFUSAL_REASONS`.
- WHEN the dispatcher receives `ResumeDeferred` THE SYSTEM SHALL defer with a reason from the closed set `RESUME_DEFERRAL_REASONS = {loop-not-ready, loop-ending, legacy-loop, implement-running, recovery-not-ready, feedback-not-ready}`. Any other reason is normalised to `unspecified`.
- IF a delivery is re-sent with the same request id after a refusal or deferral THEN THE SYSTEM SHALL validate it again and SHALL accept it at most once (`_accepted_request_ids`). It SHALL never produce two deliveries or two executions.
- IF, under the new contract, `_deliver` handles a delivery that was accepted while `_gates_passed` was already True THEN THE SYSTEM SHALL land its execution `Failed` with refusal `feedback-not-ready` and SHALL NOT land `Succeeded`. This is defence in depth: the validator already blocks this case.
- WHEN a delivery was accepted before the gates passed and the approval is then granted THE SYSTEM SHALL keep today's behaviour and land `Succeeded`.
- WHEN a history recorded before M1 (including `tests/fixtures/histories/*.json`) is replayed THE SYSTEM SHALL replay without non-determinism.
- WHEN a delivery was accepted and recorded before M1 (a `MergeWatchResume` or `OpenDelivery` carried by an old history, including a pending terminal phase) THE SYSTEM SHALL keep landing it exactly as before, including `Succeeded`. The M1 fence applies only to deliveries validated after M1 is deployed, and no existing historical expectation is rewritten.
- THE SYSTEM SHALL release a deferred request only by one of: the loop ending (a later claim starts a continuation run); the PR merging (the request is then refused `work-merged`); an operator rejecting it through the existing mctl-api `RejectExecutionRequest` endpoint (the `mctl_list_work_item_execution_requests` listing shows it as claimed); or a later slice serving it (see the next criterion).
- WHILE a request has been deferred for more than 24 hours THE SYSTEM SHALL log a WARN from the dispatcher with the request id, work item id, reason and age, once per lease re-claim. The dispatcher audit already records `resume_deferred:<reason>`. M1 adds no new command to the workflow for this.
- THE SYSTEM SHALL let a later slice serve a request deferred `feedback-not-ready` without any change to the request row: the next claim validates it again against the then-current validator. A request deferred `legacy-loop` belongs to a loop whose `deferred_resume_contract` is False for its whole life, so no later slice serves it. It leaves the slot only through the release paths above, and the operator sees `legacy-loop` as the reason.
- THE SYSTEM SHALL provide a rollback fence: before the worker is rolled back to a pre-M1 image, the dispatcher is paused (`EXECUTION_REQUEST_DISPATCHER` off) and every deferred request is either rejected by an operator or left unclaimed, so that no pre-M1 `_deliver` can receive a post-gates resume and land a false `Succeeded`.

## Out of scope
- Part M feedback tick, scope classification, shepherd integration, and the sibling GitOps CWFT PR (#993 tasks 5-8; slice M2).
- Closed-loop rewrite/rewind (M3), orphan spike/sweep (M4), global rollout status, observability, and ADR work beyond this slice.
- Part S, draft PR #992, and the implemented #991 proposal, including their branches, digests and status.
- Any release, deploy, feature-flag enablement, mctl-api queue switch, or PR merge. `DEVLOOP_DEFERRED_FEEDBACK`, `DEVLOOP_IMPLEMENT_HOLD` and `EXECUTION_ORPHAN_SWEEP_SECONDS` stay OFF and are not read by M1. mctl-api release PR #934 stays Draft.
- Acting on `expected_state_version` or `resumed_from_execution_id` beyond carrying them. They are recorded on the delivery only.

## Open questions
- A post-gates, intentful resume whose PR has not been observed yet maps to `feedback-not-ready` (deferred), not a separate reason. This keeps the vocabulary closed. The reviewer should confirm.
- A deferred request stays claimed and is re-claimed on each lease expiry. mctl-api allows one open request per item, so it occupies the item's slot until a release path above applies. The release paths, the operator view and the 24-hour WARN are now part of this proposal. The remaining cost is accepted fail-closed behaviour: an old loop (`legacy-loop`) can hold the slot for the whole merge watch (up to 14 days) unless an operator rejects the request.
- The validator answers `legacy-loop` for gates-passed loops that predate the marker, where today it answers `Succeeded`-at-once. This changes behaviour for in-flight old loops once M1 is deployed, so M1 is not inert in production: the dispatcher is already on, and new resume requests on such loops are deferred instead of falsely succeeded. The validator is replay-safe because a rejected Update writes no event and validators do not run on replay.
