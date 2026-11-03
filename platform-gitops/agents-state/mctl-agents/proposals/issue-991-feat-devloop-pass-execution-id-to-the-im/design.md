# Design: issue-991-feat-devloop-pass-execution-id-to-the-im

Amended 2026-11-03 (see requirements.md, "Amendment 2026-11-03"): corrected end-phase facts, a merge-watch retry of
a pending end-advance, the resolved after-flip semantics, deployed-state facts, rollout gate and rollback order.
The deferred-resume contract is mctl-agents#993 and is not duplicated here.

## Current state
All references are `orchestrator/temporal/workflows/dev_loop.py` unless noted.

- Canonical execution. `_run_loop` sets `self._canonical = workflow.patched(CANONICAL_APPROVAL_PATCH)`
  (~:3537). A dispatched loop pins `self._canonical_execution = dispatched.execution_id` (~:3553); any other
  canonical loop calls `_ensure_canonical_execution` (~:3342). `_canonical_execution_id()` (~:2391) returns it;
  its docstring says "the grant, the run token and the flip must all name this one".
- Investigate submit (the reference). ~:3605-3617: when `dispatched is not None or self._canonical_open`,
  `investigate_params["execution_id"] = dispatched.execution_id if dispatched is not None else
  self._canonical_execution_id()`.
- Canonical end. `_end_canonical_execution(phase)` (~:3488) advances the `we_` through
  `_advance_dispatched_execution` once; its docstring: held non-terminal "because mctl-api only binds an `aar_`
  to, mints a run token for, and resolves an approve to a NON-TERMINAL execution; it ends right after the approve
  flip". The flip-site call is ~:4157-4160 (`if self._canonical: await self._end_canonical_execution(
  self._canonical_end_phase or "Failed")`), with `_canonical_end_phase` set from the investigator's result
  (~:3663, ~:3815). `run` (~:3449-3486) ends it again on every exit if still open (`_canonical_open`), using
  `_canonical_pending_phase` when an earlier advance did not land.
- Implement submit. ~:4194-4205 builds `implement_params` (`service`, `slug`, `agent_image`, `agent_version`)
  and `update(self._launch_correlation())`. `_launch_correlation` (~:4586-4607) is gated on
  `LAUNCH_CORRELATION_PATCH` and returns `temporal_workflow_id`, `temporal_run_id`, `work_item_id`; it is also
  used for the shepherd tick (~:4970-4971). After the after-flip re-approval gate (~:4216-4231) the loop calls
  `self._implement(...)` (~:4236), whose pre-start requeue loop reuses the same params.
- After-flip re-approval. `_await_canonical_reapproval(after_flip=True)` (~:2505-2522) waits for a resume to
  open a NEW execution (`opened()`), then requests the grant on `self._executions[-1].execution_id`.
- Phases the loop writes. `_advance_dispatched_execution` is only ever called with `Succeeded` or `Failed`; the
  phase `Error` is written only by mctl-api's orphan sweeper (mctlhq/mctl-api#931). `_implement` (~:4646)
  requeues pre-start failures and otherwise raises a non-retryable `ApplicationError` for a failed, cancelled or
  timed-out run (marker `implement-outcome`, recorded by every loop new enough to record
  `IMPLEMENT_EXECUTION_PATCH`), so the code after `_implement` returns only for a succeeded run. mctl-api cannot
  tell Cancel and Timeout from Failed.
- Pending end-advance. `_end_canonical_execution` keeps `_canonical_open` and sets `_canonical_pending_phase` when
  the advance does not land. Today it is retried only by `run`'s exit paths; inside `_watch_pr` (up to
  `MERGE_WATCH_DEADLINE`, 14 days, with continue-as-new hops) nothing retries it, while `dispatcher`
  reconciliation skips a RUNNING loop and the mctl-api sweeper fails closed on a Running loop. A queued request
  would stay blocked for the whole watch.
- Runner side. `orchestrator/run_implementer.py` ~:6012-6034: `EXECUTION_ID_ENV = "WORKFLOW_EXECUTION_ID"`;
  `_setup_run_token` exits 2 under `enforce` if empty, else `run_token.setup(shadow_scope="implement")`.
  `orchestrator/run_token.py` notes a token "ends with its run, by expiry or its execution turning terminal".
- Tests. `tests/test_dev_loop_workflow.py::test_neither_submit_carries_an_execution_id` (~:5409-5446) asserts
  `"execution_id" not in implement_log[0]` and `not in shepherd_log[0]`. Replay harness:
  `tests/test_workflow_replay.py`, `tests/replay_scenarios.py` (scenario `dev_loop_full` driven by
  `_fake_activities`), fixtures `tests/fixtures/histories/dev_loop_*.json`; patch memoisation in
  `tests/test_patch_memoization.py`.

Deployed state checked:
- `$MCTL_GITOPS_ROOT/argo-workflows/cluster-templates/cwft-mctl-agents-implement.yaml`: declares parameter
  `execution_id` (default ""), maps it to env `WORKFLOW_EXECUTION_ID` (~:848), sets `MCTL_RUN_TOKEN_MODE=observe`
  (~:785) and `MCTL_RUN_TOKEN_SA_TOKEN_FILE`. No gitops change is needed.
- `$MCTL_GITOPS_ROOT/services/admins/mctl-agents-worker{,-exec,-implement}/values.yaml`: all at image tag
  `1.117.0` (tenant `admins`).
- `platform-gitops/services/admins/mctl-agents-worker/values.yaml:139` already sets
  `EXECUTION_REQUEST_DISPATCHER: "true"` (commit f1fc08233, 2026-09-24, worker image 1.117.0 era). "Off by
  default" is only the code default, so the dispatcher is not a rollout switch.
- mctl-api queue switch (mctlhq/mctl-api#931, name decided there, default off): not read from the live cluster in
  this amendment; the rollout gate requires it to be observed ON before the worker image is bumped.
- Not checked: the live Argo Workflows `mctl-agents-implement-21260455` / `-55052262` cited in the issue and the
  mctl-api side (`internal/k8s/agent_run_binding.go`); no live-cluster or mctl-api source read was made in this
  run. The issue's statement about them is taken as reported, not observed.

## Proposed solution
One new marker, `IMPLEMENT_EXECUTION_PATCH = "implement-execution-id"`, declared beside
`LAUNCH_CORRELATION_PATCH` with a comment in the same style (why, migration by attrition).

1. Decide once, at the flip site (~:4157). Replace the unconditional canonical end with:
   ```
   if self._canonical:
       self._hold_canonical_for_implement = workflow.patched(IMPLEMENT_EXECUTION_PATCH)
       if not self._hold_canonical_for_implement:
           await self._end_canonical_execution(self._canonical_end_phase or "Failed")
   ```
   Placement matters: in a pre-patch history the next command at this point is the advance activity; replaying
   with no marker makes `patched()` return False and schedules exactly that. A new history records the marker
   instead and no advance here. `self._hold_canonical_for_implement` is initialised False in `__init__`.
2. Add the id to the implement params only (~:4205), never to `_launch_correlation`, so the shepherd tick is
   untouched:
   ```
   if self._hold_canonical_for_implement:
       execution_id = self._canonical_execution_id()
       if not execution_id:
           raise ApplicationError("implement run has no canonical execution to bind its run token to",
                                  type=IMPLEMENT_EXECUTION_MISSING_ERROR_TYPE, non_retryable=True)
       implement_params["execution_id"] = execution_id
   ```
   Source: `_canonical_execution_id()` is `dispatched.execution_id` for a dispatched canonical loop and the
   ensured `we_` otherwise, i.e. the investigate source. The raise goes through `run`'s exception path, which
   ends the still-open `we_` as Failed. Because the dict is built before `_implement`'s requeue loop, every
   requeued attempt carries the same id.
3. End after the implement (~:4236, right after `_implement` returns, before the abandon check):
   ```
   if self._hold_canonical_for_implement:
       self._canonical_end_phase = "Succeeded" if implement_result.succeeded else "Failed"
       await self._end_canonical_execution(self._canonical_end_phase)
   ```
   This line runs on success only: a failed, cancelled or timed-out implement raises out of `_implement`, and
   `run`'s exception path ends the `we_` `Failed` (`_canonical_pending_phase or "Failed"`, with
   `FAST_ACTIVITY_RETRY_POLICY`). The conditional expression stays as a guard; the failure end is asserted in the
   exit path, not here. Exits between the flip and this point are covered by `run`'s two end calls.
3a. Retry a pending end-advance during the merge watch. New marker
   `IMPLEMENT_END_RETRY_PATCH = "implement-end-retry"`, declared beside `IMPLEMENT_EXECUTION_PATCH`, evaluated
   once right after the post-implement end, only under `_hold_canonical_for_implement`, and stored as
   `self._retry_pending_end`. It is a separate marker because it adds activity commands to the merge-watch
   poll loop, which histories that recorded `IMPLEMENT_EXECUTION_PATCH` alone must not replay. In `_watch_pr`, at
   the top of each poll iteration (before `get_pr_state`):
   ```
   if self._retry_pending_end and self._canonical_open and self._canonical_pending_phase:
       await self._end_canonical_execution(
           self._canonical_pending_phase, retry_policy=FAST_ACTIVITY_RETRY_POLICY)
   ```
   One attempt per poll, none once it has landed (`_canonical_open` False), so at most one extra command per
   poll and none in the common case; `FAST_ACTIVITY_RETRY_POLICY` keeps a store outage from stalling merge
   detection. Hops: before the continue-as-new branch builds `MergeWatchResume`, make one last attempt; if the
   `we_` is still open, carry `canonical_execution_id`, `canonical_open` and `canonical_pending_phase` as new
   defaulted `MergeWatchResume` fields (old resume records still decode) and rehydrate them in
   `_resume_merge_watch`, which keeps retrying. The implementer must first verify what `_resume_merge_watch`
   does with `_canonical_open` today; if the continued run already ends or abandons the `we_` another way, record
   it and keep only the retry. Poll-index cadence is unchanged, so the retry interval is the watch cadence.
4. After-flip re-approval under the marker. Pass `after_flip=not self._hold_canonical_for_implement` to
   `_await_canonical_reapproval`: under the marker the grant is requested on the still-open canonical `we_`
   (`execution_id=""`), never by waiting for `opened()`. Why this is safe: with the mctl-api queue switch on
   (mctlhq/mctl-api#931) a resume made while the `we_` is open is stored `pending` and `ClaimExecutionRequest`
   skips the work item until the `we_` closes, so no delivery reaches the loop between the flip and the end of
   implement and the gate is normally a pass-through. `after_flip=True` is retained only for histories without the
   marker and for the legacy `resume` signal (no sender in production). No extra command shape for old
   histories. What a deferred resume does after the `we_` closes is defined by mctl-agents#993, not here, and
   releasing or enabling #992 is gated on it.
5. Docstrings: update `_end_canonical_execution` and `_canonical_execution_id` to say the `we_` is held
   through the implement run under the marker, and fix the stale `_await_canonical_reapproval` and
   `_launch_correlation` docstrings (the first still describes waiting for a resume to open a new execution under
   the marker; the second should say `execution_id` is deliberately not part of it).

## Alternatives
- Mint or reuse a separate execution for the implement run (e.g. a new `we_` attached as
  `(argo, mctl-agents-implement-...)`). Rejected by the resolved clarification (option a) and by the issue
  ("never a newly invented value").
- Add `execution_id` inside `_launch_correlation`. Rejected: it also feeds the shepherd tick, which the issue
  puts out of scope, and is memoised under `LAUNCH_CORRELATION_PATCH`, whose recorded histories must not change.
- Retry the pending end only at loop exit (as in #992). Rejected: the loop is RUNNING for up to 14 days of merge
  watch, the dispatcher skips a running loop and the mctl-api sweeper fails closed on it, so a queued request
  would be blocked for that long (owner decision 7 on mctl-agents#993).
- Only add the param, keep ending the `we_` at the flip. Rejected: the exchange would bind to a terminal
  execution and mctl-api would refuse it; observe would show a refusal instead of the proof.

## Platform impact
- Migration/back-compat: migration by attrition. Running loops whose history passed the flip without the marker
  keep the old sequence for their whole life (merge watch included); only loops reaching the flip after deploy
  record it. No gitops or schema change; the CWFT already declares the parameter.
- Behaviour: the canonical `we_` stays Running for the implement duration (typically 1-10 min, bounded by the
  implement step timeout). During that window mctl-api either refuses a new execution request for the item
  (`execution_active`, queue switch off) or stores it `pending` and unclaimable (switch on, mctlhq/mctl-api#931);
  dispatcher reconciliation of closed loops is unaffected because the loop is running. The end phase now reflects
  the implement outcome (`Succeeded`, or `Failed` from the exception path) instead of the investigator's. A
  pending end-advance is retried during the merge watch.
- Risks: (1) non-determinism if the marker is placed anywhere other than the flip site - mitigated by the
  replay tests below; (2) a stuck `we_` if the post-implement advance never lands - mitigated by the
  pending-phase retry in the merge watch (marker `implement-end-retry`) and `run`'s exit retry; (3) a worker with
  the marker against an mctl-api without the queue switch widens the refusal window to the whole implement run;
  (4) a mctl-api with the switch on and a worker without #993 delivers queued resumes as a silent no-op - both
  prevented by the rollout gate below.
- Resource impact: none beyond at most one extra advance activity per merge-watch poll while an end-advance is
  pending (two markers, no new activity type; the advance activity moves position).
- Rollout gate (order matters). #992 stays in draft and `IMPLEMENT_EXECUTION_PATCH` stays unenabled until
  (1) mctlhq/mctl-api#931 is released with its queue switch on, observed; (2) the mctl-agents#993 behaviour
  exists and is integration-tested; (3) this amendment is approved with a new digest. Then: queue switch ->
  `IMPLEMENT_EXECUTION_PATCH` -> worker image bump (services/admins/mctl-agents-worker{,-exec,-implement}), with
  `EXECUTION_REQUEST_DISPATCHER` already on. Who bumps the image after the switch check is an open owner
  decision on mctl-agents#993.
- Release order: gate -> this slice -> release -> worker deploy -> first real DevLoop implement as S5 observe
  proof. Sweep/manual paths remain without `execution_id` and are not masked.
